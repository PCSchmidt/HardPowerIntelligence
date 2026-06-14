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


async def main(source: str | None, embed: bool, prune: bool) -> None:
    pool = await create_pool()
    sources = [source] if source else registered_source_ids()
    print(f"Ingesting: {', '.join(sources)}")

    exit_code = 0
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
                if result.status == "failed":
                    exit_code = 1

        if prune:
            counts = await prune_hot_window(pool)
            print(
                f"Retention: pruned {counts['normalized_records']} normalized, "
                f"{counts['raw_records']} raw records"
            )
    finally:
        await pool.close()

    sys.exit(exit_code)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=None, help="single source_id (default: all active)")
    parser.add_argument("--no-embed", dest="embed", action="store_false")
    parser.add_argument("--no-prune", dest="prune", action="store_false")
    args = parser.parse_args()
    asyncio.run(main(args.source, args.embed, args.prune))
