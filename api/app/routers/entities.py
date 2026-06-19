"""Entity endpoints (T3.4, D091) — the resolved entity graph surfaced to the reader.

Two jobs: (1) a batched summary lookup used to decorate brief items with display chips
(`name`, `ticker`, `is_private`) without an N+1; (2) `GET /entities/{id}` — the Entity 360 payload
(identifiers, the desks it spans, recent appearances). An entity with no current ticker identifier
is treated as private/venture (minted from a CIK/UEI during resolution, D092) and rendered as a
name-only chip.

Resolved entities only render because the resolver cleared its accuracy eval gate (D091
non-negotiable) — a wrong ticker would corrupt the provenance trust model.
"""
from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends

from app.deps import Principal, get_pool, get_principal
from app.errors import APIError

router = APIRouter()

# Cap recent appearances; the full cross-time history is an Entity 360 / Pro concern (T3.6).
_APPEARANCE_LIMIT = 25

# One ticker per entity (the seed keeps a single ticker; share classes collapse by CIK, D091).
_SUMMARY_SQL = """
SELECT e.id::text AS id, e.canonical_name AS name, e.entity_type AS type, t.id_value AS ticker
FROM entities e
LEFT JOIN LATERAL (
    SELECT id_value FROM entity_identifiers
    WHERE entity_id = e.id AND id_type = 'ticker' AND valid_to IS NULL
    LIMIT 1
) t ON true
WHERE e.id = ANY($1::uuid[]) AND e.is_active
"""


def entity_summary(row: asyncpg.Record | dict) -> dict:
    """Pure: a brief-item chip summary. ``is_private`` = no current ticker (minted/closely-held)."""
    ticker = row["ticker"]
    return {
        "id": row["id"],
        "name": row["name"],
        "type": row["type"],
        "ticker": ticker,
        "is_private": ticker is None,
    }


def entity_detail(
    entity: asyncpg.Record | dict,
    identifiers: list[asyncpg.Record | dict],
    appearances: list[asyncpg.Record | dict],
) -> dict:
    """Pure: the Entity 360 payload from its rows. Derives ticker, private flag, and the set of
    desks the entity spans (the cross-desk *convergence* signal, T3.7) from what it's joined to."""
    ids = [{"type": r["id_type"], "value": r["id_value"]} for r in identifiers]
    ticker = next((r["id_value"] for r in identifiers if r["id_type"] == "ticker"), None)
    # briefs.desk is a single desk string per brief; the distinct set across appearances is the
    # cross-desk convergence signal (T3.7).
    desks = sorted({r["desk"] for r in appearances if r["desk"]})
    return {
        "id": entity["id"],
        "name": entity["name"],
        "type": entity["type"],
        "ticker": ticker,
        "is_private": ticker is None,
        "identifiers": ids,
        "desks": desks,
        "convergence": len(desks) >= 2,
        "appearances": [
            {
                "brief_id": r["brief_id"],
                "desk": r["desk"],
                "date": r["date"],
                "headline": r["headline"],
                "item_type": r["item_type"],
            }
            for r in appearances
        ],
    }


async def entities_for_ids(conn: asyncpg.Connection, ids: list) -> list[dict]:
    """Batched chip summaries for a set of entity ids (order not guaranteed; caller maps by id)."""
    if not ids:
        return []
    rows = await conn.fetch(_SUMMARY_SQL, ids)
    return [entity_summary(r) for r in rows]


@router.get("/entities/{entity_id}")
async def get_entity(
    entity_id: UUID,
    principal: Principal = Depends(get_principal),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    async with pool.acquire() as conn:
        entity = await conn.fetchrow(
            "SELECT id::text AS id, canonical_name AS name, entity_type AS type "
            "FROM entities WHERE id = $1 AND is_active",
            entity_id,
        )
        if entity is None:
            raise APIError(404, "not_found", "Entity not found")
        identifiers = await conn.fetch(
            "SELECT id_type, id_value FROM entity_identifiers "
            "WHERE entity_id = $1 AND valid_to IS NULL ORDER BY id_type",
            entity_id,
        )
        appearances = await conn.fetch(
            """
            SELECT b.id::text AS brief_id, b.desk, b.date, bi.headline, bi.item_type
            FROM brief_items bi JOIN briefs b ON b.id = bi.brief_id
            WHERE bi.entity_ids @> ARRAY[$1]::uuid[] AND b.status = 'published'
            ORDER BY b.date DESC LIMIT $2
            """,
            entity_id, _APPEARANCE_LIMIT,
        )
    return entity_detail(entity, identifiers, appearances)
