"""Hot-window retention pruning (D055 §12a).

Keeps the working set small so the HNSW vector index stays fast and storage
stays bounded, while **never** breaking the provenance chain of a published
brief. Policy:

- ``normalized_records`` older than the hot window are deleted outright — nothing
  references them, and the durable record of what we said lives in ``briefs`` /
  ``citations`` (kept indefinitely).
- ``raw_records`` older than the hot window are deleted **only if unreferenced** —
  i.e. not cited by any brief and not pointed at by an entity edge, the
  resolution queue, or a (still-present) normalized record. A raw record cited by
  a kept brief is kept too, so citations never dangle.

Idempotent: running it twice is a no-op the second time.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import asyncpg
import structlog

from engine.settings import settings

log = structlog.get_logger()


async def prune_hot_window(
    pool: asyncpg.Pool, *, days: int | None = None
) -> dict[str, int]:
    """Delete data older than the hot window. Returns counts of rows removed."""
    days = days if days is not None else settings.ingest_hot_window_days
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with pool.acquire() as conn:
        async with conn.transaction():
            nr_deleted = await conn.fetchval(
                """WITH d AS (
                       DELETE FROM normalized_records
                       WHERE created_at < $1 RETURNING id
                   ) SELECT count(*) FROM d""",
                cutoff,
            )
            # Only prune raw_records with no surviving references.
            rr_deleted = await conn.fetchval(
                """WITH d AS (
                       DELETE FROM raw_records rr
                       WHERE rr.created_at < $1
                         AND NOT EXISTS (SELECT 1 FROM citations c
                                         WHERE c.raw_record_id = rr.id)
                         AND NOT EXISTS (SELECT 1 FROM normalized_records nr
                                         WHERE nr.raw_record_id = rr.id)
                         AND NOT EXISTS (SELECT 1 FROM entity_edges ee
                                         WHERE ee.source_raw_record_id = rr.id)
                         AND NOT EXISTS (SELECT 1 FROM resolution_queue rq
                                         WHERE rq.raw_record_id = rr.id)
                       RETURNING id
                   ) SELECT count(*) FROM d""",
                cutoff,
            )

    counts = {
        "normalized_records": nr_deleted or 0,
        "raw_records": rr_deleted or 0,
    }
    log.info("retention_pruned", days=days, **counts)
    return counts
