"""Convergence graph endpoint (Convergence-graph §2) — serves the CONVERGES_WITH edge layer.

Returns a *curated subgraph* (never the firehose): the top-weighted co-appearance edges under the
requested filters, plus the entity nodes those edges touch, so the web viz (§3) gets a self-contained
payload it can render directly. Filters — desk, time window, minimum confidence, cross-desk-only, and a
hard top-N cap — exist because a graph view needs a legible slice, not all N² pairs.

Edges come from ``entity_edges`` (edge_type CONVERGES_WITH, live rows only); nodes reuse the same
desk-span convergence signal the entity chips use. Authed like the other entity surfaces (any tier).
"""
from __future__ import annotations

import json
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.deps import Principal, get_pool, get_principal
from app.errors import APIError

router = APIRouter()

_DESKS = ("defense", "ai", "energy")
_DEFAULT_LIMIT = 100
_MAX_LIMIT = 500
_COAPPEARANCE_LIMIT = 12
_FUNDING_LIMIT = 60  # top AWARDED edges by dollars when the funding overlay is on

# Live CONVERGES_WITH edges under the filters, strongest first. Filters are all optional (guarded by a
# NULL/FALSE sentinel per param) so one prepared statement serves every combination. The jsonb `?`
# operator tests desk membership in the edge's stored desk array; last_seen is an ISO date string.
_EDGES_SQL = """
SELECT ef.from_entity_id::text          AS from_id,
       ef.to_entity_id::text            AS to_id,
       ef.confidence                    AS confidence,
       (ef.properties->>'weight')::float   AS weight,
       (ef.properties->>'co_count')::int   AS co_count,
       ef.properties->'desks'           AS desks,
       (ef.properties->>'cross_desk')::bool AS cross_desk,
       ef.properties->>'last_seen'      AS last_seen
FROM entity_edges ef
WHERE ef.edge_type = 'CONVERGES_WITH' AND ef.valid_to IS NULL
  AND ef.confidence >= $1
  AND ($2 = FALSE OR (ef.properties->>'cross_desk')::bool)
  AND ($3::text IS NULL OR ef.properties->'desks' ? $3)
  AND ($4::int IS NULL OR (ef.properties->>'last_seen')::date >= CURRENT_DATE - $4)
ORDER BY ef.confidence DESC, weight DESC
LIMIT $5
"""

# The largest AWARDED (agency → company) funding edges (Convergence-graph §5 overlay). Federal
# contractors barely overlap the rare-earth convergence cluster, so funding is a full overlay (its own
# agency-hub subgraph shown alongside), ranked by dollars so the toggle surfaces the biggest relationships.
_FUNDING_EDGES_SQL = """
SELECT ef.from_entity_id::text          AS from_id,
       ef.to_entity_id::text            AS to_id,
       (ef.properties->>'total_usd')::float AS total_usd,
       (ef.properties->>'award_count')::int AS award_count,
       ef.properties->>'agency'         AS agency
FROM entity_edges ef
WHERE ef.edge_type = 'AWARDED' AND ef.valid_to IS NULL
ORDER BY (ef.properties->>'total_usd')::float DESC NULLS LAST
LIMIT $1
"""

# Node summary for the entities the returned edges touch — name, one ticker, entity kind, and the
# distinct published-brief desks it spans (the cross-desk convergence signal, mirrors entities._SUMMARY_SQL).
_NODES_SQL = """
SELECT e.id::text AS id, e.canonical_name AS name, e.entity_type AS entity_type,
       t.id_value AS ticker, d.desks AS desks
FROM entities e
LEFT JOIN LATERAL (
    SELECT id_value FROM entity_identifiers
    WHERE entity_id = e.id AND id_type = 'ticker' AND valid_to IS NULL LIMIT 1
) t ON true
LEFT JOIN LATERAL (
    SELECT array_agg(DISTINCT b.desk) AS desks
    FROM brief_items bi JOIN briefs b ON b.id = bi.brief_id
    WHERE bi.entity_ids @> ARRAY[e.id] AND b.status = 'published'
) d ON true
WHERE e.id = ANY($1::uuid[]) AND e.is_active
"""


def _as_list(value) -> list:
    """asyncpg hands back a jsonb sub-access as text; parse to a list, tolerate an already-parsed one."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return []
    return list(value) if value else []


def edge_payload(row: asyncpg.Record | dict) -> dict:
    """Pure: one convergence (co-appearance) edge for the web."""
    return {
        "from": row["from_id"],
        "to": row["to_id"],
        "type": "converges",
        "confidence": round(float(row["confidence"]), 4),
        "weight": round(float(row["weight"]), 4),
        "co_count": row["co_count"],
        "desks": _as_list(row["desks"]),
        "cross_desk": bool(row["cross_desk"]),
        "last_seen": row["last_seen"],
    }


def funding_edge_payload(row: asyncpg.Record | dict) -> dict:
    """Pure: one AWARDED (agency → company) funding edge for the web (§5)."""
    return {
        "from": row["from_id"],
        "to": row["to_id"],
        "type": "awarded",
        "amount_usd": row["total_usd"],
        "award_count": row["award_count"],
        "agency": row["agency"],
    }


def node_payload(row: asyncpg.Record | dict) -> dict:
    """Pure: one graph node. ``kind`` distinguishes agencies; ``is_private`` = no ticker; ``convergence``
    = spans ≥2 desks."""
    ticker = row["ticker"]
    desks = sorted(row["desks"] or [])
    kind = "agency" if row["entity_type"] == "gov_agency" else "company"
    return {
        "id": row["id"],
        "name": row["name"],
        "kind": kind,
        "ticker": ticker,
        "is_private": ticker is None,
        "desks": desks,
        "convergence": len(desks) >= 2,
    }


def graph_payload(edge_rows: list, funding_rows: list, node_rows: list) -> dict:
    """Pure: assemble the {nodes, edges, meta} payload from the convergence, funding, and node rows."""
    edges = [edge_payload(r) for r in edge_rows] + [funding_edge_payload(r) for r in funding_rows]
    nodes = [node_payload(r) for r in node_rows]
    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "cross_desk_edges": sum(1 for r in edge_rows if bool(r["cross_desk"])),
            "funding_edges": len(funding_rows),
        },
    }


# The published items where BOTH entities appear — the evidence behind a CONVERGES_WITH edge
# ("why are these two connected?"). entity_ids @> ARRAY[a,b] is GIN-indexed (brief_items_entity_ids_gin).
_COAPPEARANCES_SQL = """
SELECT b.desk AS desk, b.date AS date, bi.headline AS headline, bi.item_type AS item_type
FROM brief_items bi JOIN briefs b ON b.id = bi.brief_id
WHERE b.status = 'published' AND bi.entity_ids @> ARRAY[$1, $2]::uuid[]
ORDER BY b.date DESC, bi.display_order
LIMIT $3
"""


def coappearance_payload(rows: list) -> dict:
    """Pure: the shared-story list shown when hovering an edge."""
    return {
        "count": len(rows),
        "items": [
            {
                "desk": r["desk"],
                "date": str(r["date"]),
                "headline": r["headline"],
                "item_type": r["item_type"],
            }
            for r in rows
        ],
    }


@router.get("/graph/co-appearances")
async def get_edge_coappearances(
    a: UUID,
    b: UUID,
    principal: Principal = Depends(get_principal),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    """The published items where entities ``a`` and ``b`` both appear — the evidence behind an edge."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(_COAPPEARANCES_SQL, a, b, _COAPPEARANCE_LIMIT)
    return coappearance_payload(rows)


@router.get("/graph/convergence")
async def get_convergence_graph(
    desk: str | None = Query(default=None),
    days: int | None = Query(default=None, gt=0),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    cross_desk_only: bool = Query(default=False),
    funding: bool = Query(default=False),
    limit: int = Query(default=_DEFAULT_LIMIT, gt=0),
    principal: Principal = Depends(get_principal),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    if desk is not None and desk not in _DESKS:
        raise APIError(422, "invalid_desk", f"desk must be one of {', '.join(_DESKS)}")
    limit = min(limit, _MAX_LIMIT)

    async with pool.acquire() as conn:
        edge_rows = await conn.fetch(
            _EDGES_SQL, min_confidence, cross_desk_only, desk, days, limit
        )
        company_ids = {r["from_id"] for r in edge_rows} | {r["to_id"] for r in edge_rows}
        # §5: overlay the federal-funding subgraph (top AWARDED edges by dollars) — its agencies AND the
        # companies they fund become nodes, shown alongside the convergence web. Off by default (clean).
        funding_rows = await conn.fetch(_FUNDING_EDGES_SQL, _FUNDING_LIMIT) if funding else []
        node_ids = list(
            company_ids
            | {r["from_id"] for r in funding_rows}
            | {r["to_id"] for r in funding_rows}
        )
        node_rows = await conn.fetch(_NODES_SQL, node_ids) if node_ids else []

    return graph_payload(edge_rows, funding_rows, node_rows)
