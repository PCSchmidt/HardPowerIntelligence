"""Production ingestion runner (D004, D055).

Drives one source end-to-end: read its ``source_registry`` config + cursor,
page through the live API via :class:`HttpFetcher`, dedup into ``raw_records``,
normalize into ``normalized_records``, embed the new chunks, advance the cursor,
and record an ``ingestion_runs`` row for provenance. This is the live-data
replacement for ``scripts/seed_fixtures.py``.

Design notes:
- **Dedup is deterministic.** ``raw_records`` has ``UNIQUE (source_id, native_id,
  content_hash)``; we INSERT ... ON CONFLICT DO NOTHING RETURNING id. A returned
  id means the row was new, so we only build a ``normalized_record`` (and pay to
  embed it) for genuinely new content. Re-runs are cheap and idempotent.
- **Accounting first.** An ``ingestion_runs`` row is opened ``running`` before any
  network call and always closed (``success`` / ``failed`` / ``skipped``), so a
  crash leaves a visible failed run, not silence.
- **Circuit breaker.** Repeated failures open the breaker (``source_registry``);
  an open breaker skips the run until a cooldown elapses, then tries once
  (half-open). Success resets it.
- **Embedding is gated.** It costs money (OpenAI), so it only runs when an API key
  is configured and ``embed=True``; otherwise the generator embeds lazily later.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import asyncpg
import structlog

from engine.adapters.registry import get_adapter
from engine.brief.rag import embed_pending_records
from engine.settings import settings

log = structlog.get_logger()

# How long an open breaker waits before a half-open trial.
_BREAKER_COOLDOWN = timedelta(minutes=30)


@dataclass
class RunResult:
    source_id: str
    run_id: str
    status: str                       # success | failed | skipped
    pages_fetched: int = 0
    records_fetched: int = 0
    records_new: int = 0
    records_duplicate: int = 0
    records_embedded: int = 0
    error: str | None = None
    final_cursor: dict | None = field(default=None)


async def _load_source(conn: asyncpg.Connection, source_id: str) -> asyncpg.Record:
    row = await conn.fetchrow(
        "SELECT * FROM source_registry WHERE id = $1", source_id
    )
    if row is None:
        raise KeyError(f"source_registry has no row for source_id={source_id!r}")
    return row


def _breaker_blocks(src: asyncpg.Record, now: datetime) -> bool:
    """True if the circuit breaker is open and still inside its cooldown."""
    if src["circuit_breaker_state"] != "open":
        return False
    opened = src["circuit_breaker_opened_at"]
    if opened is None:
        return True
    return (now - opened) < _BREAKER_COOLDOWN


async def _persist_page(
    conn: asyncpg.Connection,
    records: list,
    run_id: str,
    fetched_at: datetime,
) -> tuple[int, int]:
    """Insert a page of records. Returns (new, duplicate) counts.

    Only new raw_records get a normalized_record — a duplicate raw_record already
    has one from the run that first saw it, so we never double-normalize/embed.
    """
    new = dup = 0
    for rec in records:
        rr_id = str(uuid.uuid4())
        payload = json.dumps(rec.structured_data)
        inserted = await conn.fetchval(
            """
            INSERT INTO raw_records (
                id, source_id, native_id, url, fetched_at,
                content_hash, payload, payload_size_bytes, ingestion_run_id
            ) VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9)
            ON CONFLICT (source_id, native_id, content_hash) DO NOTHING
            RETURNING id
            """,
            rr_id, rec.source_id, rec.native_id, rec.url, fetched_at,
            rec.content_hash, payload, len(payload.encode()), run_id,
        )
        if inserted is None:
            dup += 1
            continue
        new += 1
        await conn.execute(
            """
            INSERT INTO normalized_records (
                id, raw_record_id, source_id, record_type, desk,
                entity_mentions, structured_data, text_chunk
            ) VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8)
            """,
            str(uuid.uuid4()), rr_id, rec.source_id, rec.record_type, rec.desk,
            json.dumps(rec.entity_mentions), payload, rec.text_chunk,
        )
    return new, dup


async def run_source(
    source_id: str,
    pool: asyncpg.Pool,
    *,
    fetcher,
    max_pages: int | None = None,
    embed: bool = True,
) -> RunResult:
    """Ingest one source end-to-end. Never raises for ingestion failures —
    failures are recorded on the run and returned as ``status='failed'`` so a
    multi-source schedule isn't aborted by one bad source. Programmer errors
    (unknown source/adapter) still raise."""
    max_pages = max_pages or settings.ingest_max_pages
    now = datetime.now(timezone.utc)
    run_id = str(uuid.uuid4())

    async with pool.acquire() as conn:
        src = await _load_source(conn, source_id)
        if not src["is_active"]:
            log.info("ingest_skip_inactive", source_id=source_id)
            return RunResult(source_id, run_id, "skipped", error="inactive")
        if _breaker_blocks(src, now):
            log.warning("ingest_skip_breaker_open", source_id=source_id)
            await conn.execute(
                """INSERT INTO ingestion_runs (id, source_id, started_at,
                   completed_at, status, error_message)
                   VALUES ($1,$2,$3,$3,'skipped','circuit breaker open')""",
                run_id, source_id, now,
            )
            return RunResult(source_id, run_id, "skipped", error="breaker_open")

        adapter = get_adapter(source_id)  # raises KeyError if unbuilt — fail loud
        cursor = src["last_cursor"]
        if isinstance(cursor, str):
            cursor = json.loads(cursor)

        await conn.execute(
            """INSERT INTO ingestion_runs (id, source_id, started_at, status)
               VALUES ($1,$2,$3,'running')""",
            run_id, source_id, now,
        )

    result = RunResult(source_id, run_id, "success")
    final_cursor: dict | None = None

    try:
        async with pool.acquire() as conn:
            page = 1
            while page <= max_pages:
                payload = adapter.build_request_payload(cursor, page)
                kwargs = {"json": payload} if adapter.http_method == "POST" else {"params": payload}
                response = await fetcher.fetch_json(
                    adapter.http_method, adapter.base_url, **kwargs
                )
                records = adapter.parse(response)
                result.pages_fetched += 1
                result.records_fetched += len(records)

                new, dup = await _persist_page(conn, records, run_id, now)
                result.records_new += new
                result.records_duplicate += dup

                nxt = adapter.next_cursor(response, page)
                if nxt and "page" in nxt:
                    page = nxt["page"]
                else:
                    final_cursor = nxt
                    break
            else:
                # Hit max_pages — persist a date-advancing cursor so the next run
                # doesn't replay the same first pages forever.
                final_cursor = adapter.next_cursor({}, page)

        if embed and settings.openai_api_key:
            since = now - timedelta(days=settings.ingest_hot_window_days)
            result.records_embedded = await embed_pending_records(pool, since)

    except Exception as exc:  # noqa: BLE001 — record + classify, don't crash the schedule
        result.status = "failed"
        result.error = f"{type(exc).__name__}: {exc}"
        log.error("ingest_failed", source_id=source_id, error=result.error)
        await _finalize_failed(pool, run_id, source_id, result)
        return result

    result.final_cursor = final_cursor
    await _finalize_success(pool, run_id, source_id, result, final_cursor, now)
    log.info(
        "ingest_complete", source_id=source_id, new=result.records_new,
        dup=result.records_duplicate, embedded=result.records_embedded,
    )
    return result


async def _finalize_success(
    pool: asyncpg.Pool,
    run_id: str,
    source_id: str,
    result: RunResult,
    final_cursor: dict | None,
    now: datetime,
) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """UPDATE ingestion_runs SET completed_at = now(), status = 'success',
                   records_fetched = $2, records_new = $3, records_duplicate = $4
                   WHERE id = $1""",
                run_id, result.records_fetched, result.records_new,
                result.records_duplicate,
            )
            await conn.execute(
                """UPDATE source_registry SET
                   last_cursor = $2::jsonb,
                   last_successful_fetch_at = $3,
                   circuit_breaker_state = 'closed',
                   circuit_breaker_failures = 0,
                   circuit_breaker_opened_at = NULL,
                   updated_at = now()
                   WHERE id = $1""",
                source_id,
                json.dumps(final_cursor) if final_cursor is not None else None,
                now,
            )


async def _finalize_failed(
    pool: asyncpg.Pool, run_id: str, source_id: str, result: RunResult
) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """UPDATE ingestion_runs SET completed_at = now(), status = 'failed',
                   records_fetched = $2, records_new = $3, records_duplicate = $4,
                   error_message = $5 WHERE id = $1""",
                run_id, result.records_fetched, result.records_new,
                result.records_duplicate, result.error,
            )
            # Increment breaker; open it once failures reach the threshold.
            await conn.execute(
                """UPDATE source_registry SET
                   circuit_breaker_failures = circuit_breaker_failures + 1,
                   circuit_breaker_state = CASE
                       WHEN circuit_breaker_failures + 1 >= circuit_breaker_threshold
                       THEN 'open' ELSE circuit_breaker_state END,
                   circuit_breaker_opened_at = CASE
                       WHEN circuit_breaker_failures + 1 >= circuit_breaker_threshold
                       THEN now() ELSE circuit_breaker_opened_at END,
                   updated_at = now()
                   WHERE id = $1""",
                source_id,
            )
