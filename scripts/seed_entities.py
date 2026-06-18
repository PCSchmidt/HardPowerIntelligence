"""Seed the reference entity set from SEC company_tickers.json (T3.1, D091).

Operator-run (writes to the cloud DB). Idempotent: existing tickers are skipped, so re-runs only
add newly-listed companies. Seeds the PUBLIC universe (the resolver's target set); private /
venture / gov entities are minted later from ingest identifiers (UEI/CIK) during resolution
(D091). Embeddings are deliberately deferred — resolution v1 uses the pg_trgm indexes on
canonical_name / alias_normalized, so entity_aliases.embedding stays NULL for now.

    uv run python scripts/seed_entities.py
"""
import asyncio
import sys
from datetime import datetime, timezone

import httpx

from engine.db import create_pool
from engine.entity.reference import SEC_COMPANY_TICKERS_URL, parse_company_tickers
from engine.settings import settings

# Chained insert: create the entity, its ticker+cik identifiers, and its normalized alias in a
# single round-trip. Pre-filtering on existing tickers (plus the one wrapping transaction) keeps
# re-runs clean, so no ON CONFLICT gymnastics are needed here.
_SEED_SQL = """
WITH e AS (
    INSERT INTO entities (canonical_name, entity_type, desk)
    VALUES ($1, 'company', '{}')
    RETURNING id
),
ids AS (
    INSERT INTO entity_identifiers (entity_id, id_type, id_value, source, valid_from)
    SELECT id, 'ticker', $2, 'sec_company_tickers', $5 FROM e
    UNION ALL
    SELECT id, 'cik', $3, 'sec_company_tickers', $5 FROM e
)
INSERT INTO entity_aliases (entity_id, alias, alias_normalized, source)
SELECT id, $4, $6, 'sec_company_tickers' FROM e
"""


async def main() -> int:
    headers = {"User-Agent": settings.edgar_user_agent}
    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        resp = await client.get(SEC_COMPANY_TICKERS_URL)
        resp.raise_for_status()
        payload = resp.json()

    refs = parse_company_tickers(payload)
    print(f"Parsed {len(refs)} public companies from SEC.")
    if not refs:
        print("No companies parsed — aborting (SEC payload shape may have changed).")
        return 1

    now = datetime.now(timezone.utc)
    pool = await create_pool()
    inserted = skipped = 0
    try:
        async with pool.acquire() as conn:
            existing = {
                r["id_value"]
                for r in await conn.fetch(
                    "SELECT id_value FROM entity_identifiers WHERE id_type = 'ticker'"
                )
            }
            print(f"Existing seeded tickers: {len(existing)}")
            async with conn.transaction():
                for ref in refs:
                    if ref.ticker in existing:
                        skipped += 1
                        continue
                    await conn.execute(
                        _SEED_SQL,
                        ref.name, ref.ticker, ref.cik, ref.name, now, ref.name_normalized,
                    )
                    inserted += 1
        print(f"Done: inserted={inserted}, skipped(existing ticker)={skipped}")
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
