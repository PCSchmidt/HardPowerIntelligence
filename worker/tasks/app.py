"""hpi-worker — persistent ingestion process (D116).

GDELT rate-limits the shared GitHub Actions IP with HTTP 429 regardless of User-Agent
(the D110 UA fix held for one day, then 2026-07-02 429'd again). A persistent server IP
is the documented cure — it's why SITREP pulls GDELT cleanly from its always-on scheduler.

This worker is that persistent home: a single always-on Fly machine (IAD) that ingests the
worker-owned sources (GDELT) into the SHARED database on an interval, so brief generation —
still in CI — reads fresh news from the DB. GDELT is excluded from the CI ingest entirely
(scripts/run_ingest.py --exclude gdelt): not just to avoid the 429 noise, but because the
circuit breaker is keyed by source_id in the shared source_registry — repeated CI failures
would open GDELT's breaker and block THIS worker too.

Design is deliberately minimal (project value: simple > clever): a plain asyncio interval
loop, no task-queue framework (the pyproject's old procrastinate dep is dropped). One
always-on machine only — `fly scale count 1`; a second would double-ingest. Everything is
wrapped so a single failed pull logs and waits for the next tick rather than crashing the
process (which Fly would then restart-loop).
"""
from __future__ import annotations

import asyncio
import os

import httpx
import structlog

from engine.db import create_pool
from engine.ingest.fetcher import HttpFetcher
from engine.ingest.runner import run_source

log = structlog.get_logger()

# Sources this worker owns (kept off CI due to shared-IP rate limiting). GDELT today; the
# same persistent-IP argument would extend to any future scrape-sensitive source.
WORKER_SOURCES: tuple[str, ...] = ("gdelt",)

# How often to pull. 3h keeps DB news < 3h stale for the daily brief without hammering the
# API; override with WORKER_INGEST_INTERVAL_SECONDS (tests set it small).
DEFAULT_INTERVAL_SECONDS = 3 * 60 * 60


def _interval_seconds() -> int:
    try:
        return max(60, int(os.environ.get("WORKER_INGEST_INTERVAL_SECONDS", "")))
    except ValueError:
        return DEFAULT_INTERVAL_SECONDS


async def ingest_once(pool, *, embed: bool | None = None) -> list[str]:
    """Ingest every worker-owned source once into the shared DB. Never raises: a source
    failure is logged and swallowed so the scheduler loop keeps running. Returns the per
    source statuses (for tests / observability)."""
    if embed is None:
        embed = bool(os.environ.get("OPENAI_API_KEY"))
    statuses: list[str] = []
    async with httpx.AsyncClient() as client:
        fetcher = HttpFetcher(client)
        for sid in WORKER_SOURCES:
            try:
                result = await run_source(sid, pool, fetcher=fetcher, embed=embed)
                statuses.append(result.status)
                log.info(
                    "worker_ingest", source=sid, status=result.status,
                    new=result.records_new, fetched=result.records_fetched,
                )
            except Exception as exc:  # noqa: BLE001 — a bad pull must never kill the scheduler
                statuses.append("failed")
                log.error("worker_ingest_failed", source=sid, error=str(exc))
    return statuses


async def run_forever() -> None:
    interval = _interval_seconds()
    log.info("worker_starting", sources=list(WORKER_SOURCES), interval_seconds=interval)
    pool = await create_pool()
    try:
        while True:
            # Pull immediately on boot too, so a fresh deploy populates data without waiting
            # a full interval — the fastest way to confirm the persistent IP clears GDELT.
            await ingest_once(pool)
            await asyncio.sleep(interval)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(run_forever())
