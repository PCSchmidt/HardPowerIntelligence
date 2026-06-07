"""Catalyst calendar — upcoming events, all tiers."""
from __future__ import annotations

from datetime import date, timedelta

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.deps import Principal, get_pool, get_principal

router = APIRouter()


@router.get("/calendar")
async def calendar(
    desk: str | None = Query(None),
    from_: date | None = Query(None, alias="from"),
    to: date | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    principal: Principal = Depends(get_principal),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    start = from_ or date.today()
    end = to or (start + timedelta(days=30))

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, desk, event_type, title, event_date, event_time_utc,
                   source_url, entity_ids
            FROM calendar_events
            WHERE event_date BETWEEN $2 AND $3
              AND ($1::text IS NULL OR $1 = ANY(desk))
            ORDER BY event_date, event_time_utc NULLS LAST
            LIMIT $4
            """,
            desk, start, end, limit,
        )

    return {
        "events": [
            {
                "id": str(r["id"]),
                "event_type": r["event_type"],
                "title": r["title"],
                "event_date": r["event_date"],
                "event_time_utc": r["event_time_utc"],
                "desk": list(r["desk"] or []),
                "entity_ids": [str(e) for e in (r["entity_ids"] or [])],
                "source_url": r["source_url"],
            }
            for r in rows
        ]
    }
