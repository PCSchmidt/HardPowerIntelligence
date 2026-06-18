"""Seed the reference entity set from SEC company_tickers.json (T3.1, D091).

Operator-run (writes to the cloud DB). Resilient + idempotent: inserts in small batches via
``executemany`` (pipelined, short-lived connections so a pooled connection isn't held open for a
huge transaction — the failure mode that aborted the first attempt), retries transient connection
drops per batch, and guards each insert with a NOT EXISTS check so re-runs and retries never create
duplicate entities. Seeds the PUBLIC universe (the resolver's target set); private / venture / gov
entities are minted later from ingest identifiers (UEI/CIK) during resolution (D091). Embeddings are
deferred — resolution v1 uses the pg_trgm indexes, so entity_aliases.embedding stays NULL.

    uv run python scripts/seed_entities.py
"""
import asyncio
import sys

import asyncpg
import httpx

from engine.db import create_pool
from engine.entity.reference import SEC_COMPANY_TICKERS_URL, parse_company_tickers
from engine.settings import settings

_BATCH = 200
_MAX_ATTEMPTS = 4
# Connection-drop errors worth retrying (WinError 1236 etc. surface as OSError; asyncpg raises
# ConnectionDoesNotExistError / InterfaceError off a closed connection). SQL errors are not caught,
# so a real bug fails fast instead of retrying.
_RETRYABLE = (
    OSError,
    asyncpg.exceptions.InterfaceError,
    asyncpg.exceptions.ConnectionDoesNotExistError,
)

# Idempotent per ticker: the NOT EXISTS guard means a re-run (or a batch retry after a lost commit
# ack) inserts nothing for tickers already present — no duplicate entities.
_SEED_SQL = """
WITH dup AS (
    SELECT 1 FROM entity_identifiers WHERE id_type = 'ticker' AND id_value = $2 LIMIT 1
),
e AS (
    INSERT INTO entities (canonical_name, entity_type, desk)
    SELECT $1, 'company', '{}'::text[] WHERE NOT EXISTS (SELECT 1 FROM dup)
    RETURNING id
),
ids AS (
    INSERT INTO entity_identifiers (entity_id, id_type, id_value, source, valid_from)
    SELECT id, 'ticker', $2, 'sec_company_tickers', now() FROM e
    UNION ALL
    SELECT id, 'cik', $3, 'sec_company_tickers', now() FROM e
)
INSERT INTO entity_aliases (entity_id, alias, alias_normalized, source)
SELECT id, $4, $5, 'sec_company_tickers' FROM e
"""


async def _seed_batch(pool: asyncpg.Pool, batch: list) -> None:
    args = [(r.name, r.ticker, r.cik, r.name, r.name_normalized) for r in batch]
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.executemany(_SEED_SQL, args)


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

    pool = await create_pool()
    try:
        async with pool.acquire() as conn:
            existing = {
                r["id_value"]
                for r in await conn.fetch(
                    "SELECT id_value FROM entity_identifiers WHERE id_type = 'ticker'"
                )
            }
        todo = [r for r in refs if r.ticker not in existing]
        skipped = len(refs) - len(todo)
        print(f"Already seeded: {len(existing)} | to insert: {len(todo)} | skipped: {skipped}")

        inserted = 0
        for start in range(0, len(todo), _BATCH):
            batch = todo[start : start + _BATCH]
            for attempt in range(1, _MAX_ATTEMPTS + 1):
                try:
                    await _seed_batch(pool, batch)
                    inserted += len(batch)
                    break
                except _RETRYABLE as exc:
                    if attempt == _MAX_ATTEMPTS:
                        raise
                    print(f"  batch @{start} attempt {attempt} failed ({type(exc).__name__}); retrying…")
                    await asyncio.sleep(2 * attempt)
            print(f"  progress: {inserted}/{len(todo)}")
        print(f"Done: inserted={inserted}, skipped={skipped}")
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
