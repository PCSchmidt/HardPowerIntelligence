"""Production ingestion run (D004, D055).

Pulls fresh data from live source APIs into raw_records + normalized_records,
embeds new chunks, advances each source's cursor, and prunes the hot window.
This replaces scripts/seed_fixtures.py for live operation; run it before
scripts/run_brief.py so the brief synthesizes from fresh data.

Usage:
    python scripts/run_ingest.py                       # all active registered sources
    python scripts/run_ingest.py --source usaspending  # one source
    python scripts/run_ingest.py --no-embed            # skip embeddings (no OpenAI cost)
    python scripts/run_ingest.py --no-prune            # skip retention pruning
    python scripts/run_ingest.py --reset-cursor        # re-pull the full lookback window
                                                       # (e.g. after changing a source's filter)

Requires: DATABASE_URL in .env; OPENAI_API_KEY for embeddings.
"""
import argparse
import asyncio
import sys

import httpx

sys.path.insert(0, "engine")

from engine.adapters.registry import registered_source_ids
from engine.db import create_pool
from engine.ingest.fetcher import HttpFetcher
from engine.ingest.retention import prune_hot_window
from engine.ingest.runner import run_source


def decide_exit_code(statuses: list[str]) -> int:
    """Non-zero only on a TOTAL ingest failure (D079).

    A single source failing is usually transient and external — e.g. SEC EFTS
    returning 500s — and must NOT abort the daily job: briefs still publish from data
    already in the DB. So we exit non-zero only when *every* source failed (a likely
    systemic problem, e.g. the database is unreachable). Partial failures are logged
    and surfaced in the summary, but the pipeline proceeds to the brief step."""
    if not statuses:
        return 0
    return 1 if all(s == "failed" for s in statuses) else 0


async def main(source: str | None, embed: bool, prune: bool, reset_cursor: bool) -> None:
    pool = await create_pool()
    sources = [source] if source else registered_source_ids()
    print(f"Ingesting: {', '.join(sources)}")

    if reset_cursor:
        # Clear the watermark so the next pull re-fetches the full lookback window.
        # Non-destructive: dedup (content_hash) still skips already-stored records.
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE source_registry SET last_cursor = NULL WHERE id = ANY($1::text[])",
                sources,
            )
        print(f"Reset cursor for: {', '.join(sources)}")

    statuses: list[str] = []
    try:
        async with httpx.AsyncClient() as client:
            fetcher = HttpFetcher(client)
            for sid in sources:
                result = await run_source(sid, pool, fetcher=fetcher, embed=embed)
                marker = {"success": "✓", "skipped": "•"}.get(result.status, "✗")
                print(
                    f"  {marker} {sid}: status={result.status} "
                    f"fetched={result.records_fetched} new={result.records_new} "
                    f"dup={result.records_duplicate} embedded={result.records_embedded}"
                    + (f" error={result.error}" if result.error else "")
                )
                statuses.append(result.status)

        ok = statuses.count("success")
        failed = statuses.count("failed")
        skipped = statuses.count("skipped")
        print(f"Ingest summary: {ok} ok, {skipped} skipped, {failed} failed "
              f"(of {len(statuses)}).")

        if prune:
            counts = await prune_hot_window(pool)
            print(
                f"Retention: pruned {counts['normalized_records']} normalized, "
                f"{counts['raw_records']} raw records"
            )
    finally:
        await pool.close()

    sys.exit(decide_exit_code(statuses))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=None, help="single source_id (default: all active)")
    parser.add_argument("--no-embed", dest="embed", action="store_false")
    parser.add_argument("--no-prune", dest="prune", action="store_false")
    parser.add_argument("--reset-cursor", dest="reset_cursor", action="store_true",
                        help="clear the cursor first to re-pull the full lookback window")
    args = parser.parse_args()
    asyncio.run(main(args.source, args.embed, args.prune, args.reset_cursor))
