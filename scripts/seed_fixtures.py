"""
Seed the local Supabase DB with golden USAspending fixture records.
Run this before scripts/run_brief.py for the Gate 5 integration run.

Usage:
    python scripts/seed_fixtures.py

Requires: local Supabase running (supabase start), DATABASE_URL in .env
"""
import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import asyncpg

sys.path.insert(0, "engine")

from engine.adapters.usaspending import USASpendingAdapter
from engine.settings import settings

FIXTURE_PATH = Path("tests/fixtures/usaspending/20260605_awards_response.json")


async def main() -> None:
    db_url = settings.database_url.replace("+asyncpg", "")
    pool = await asyncpg.create_pool(db_url)

    fixture = json.loads(FIXTURE_PATH.read_text())
    adapter = USASpendingAdapter()
    records = adapter.parse(fixture)

    print(f"Parsed {len(records)} records from fixture.")

    run_id = str(uuid.uuid4())
    fetched_at = datetime(2026, 6, 5, 8, 0, 0, tzinfo=timezone.utc)

    async with pool.acquire() as conn:
        # Create an ingestion run for provenance
        await conn.execute(
            """
            INSERT INTO ingestion_runs (id, source_id, started_at, completed_at,
                status, records_fetched, records_new)
            VALUES ($1, 'usaspending', $2, $2, 'success', $3, $3)
            ON CONFLICT DO NOTHING
            """,
            run_id, fetched_at, len(records),
        )

        inserted_rr = 0
        inserted_nr = 0

        for rec in records:
            rr_id = str(uuid.uuid4())
            payload = json.dumps(rec.structured_data)
            payload_bytes = len(payload.encode())

            # Insert raw_record
            try:
                await conn.execute(
                    """
                    INSERT INTO raw_records (
                        id, source_id, native_id, url, fetched_at,
                        content_hash, payload, payload_size_bytes, ingestion_run_id
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9)
                    ON CONFLICT (source_id, native_id, content_hash) DO NOTHING
                    """,
                    rr_id,
                    rec.source_id,
                    rec.native_id,
                    rec.url,
                    fetched_at,
                    rec.content_hash,
                    payload,
                    payload_bytes,
                    run_id,
                )
                inserted_rr += 1
            except Exception as e:
                print(f"  raw_record skip ({rec.native_id}): {e}")
                continue

            # Insert normalized_record
            nr_id = str(uuid.uuid4())
            try:
                await conn.execute(
                    """
                    INSERT INTO normalized_records (
                        id, raw_record_id, source_id, record_type, desk,
                        entity_mentions, structured_data, text_chunk
                    ) VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8)
                    """,
                    nr_id,
                    rr_id,
                    rec.source_id,
                    rec.record_type,
                    rec.desk,
                    json.dumps(rec.entity_mentions),
                    json.dumps(rec.structured_data),
                    rec.text_chunk,
                )
                inserted_nr += 1
                print(f"  + {rec.native_id}: {rec.structured_data.get('recipient_name', '')[:40]}")
            except Exception as e:
                print(f"  normalized_record skip ({rec.native_id}): {e}")

    print(f"\nSeeded: {inserted_rr} raw_records, {inserted_nr} normalized_records")
    print("Ready to run: python scripts/run_brief.py --desk defense")
    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
