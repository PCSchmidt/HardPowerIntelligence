"""Federal-funding edges for the graph (Convergence-graph §5, first cut — 2026-07-17).

The convergence layer answers "what recurs together." This adds the first *semantic* relationship the
structured data actually carries: **AWARDED** — which federal agency funds which company, from
USAspending (`awarding_agency` → `recipient_uei`). Agencies become `gov_agency` entity nodes (a type
the schema already allows) and each (agency, recipient) pair a directed AWARDED edge weighted by total
obligated dollars. This is honest, structured, LLM-free signal: a company's federal backers and the
companies an agency's portfolio spans. (Company↔company relations like SUPPLIES/COMPETES_WITH aren't in
the structured data — those await a separate, eval-gated LLM text-extraction pass.)

Pure aggregation (unit-tested) is separated from the DB mint/upsert. Idempotent, mirroring the
convergence builder: upsert on the live-pair unique index, retire AWARDED edges that no longer appear.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Award:
    total_usd: float = 0.0
    award_count: int = 0
    last_award: str | None = None


def _to_float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def aggregate_awards(
    records: Iterable[dict],
    uei_to_entity: dict[str, str],
) -> dict[tuple[str, str], Award]:
    """Pure: fold USAspending structured_data dicts into ``{(agency, recipient_entity_id): Award}``.

    A record contributes only when its ``recipient_uei`` resolves to a known entity and it names an
    ``awarding_agency``. Dollars accumulate; the most recent ``start_date`` is kept.
    """
    agg: dict[tuple[str, str], Award] = {}
    for sd in records:
        uei = (sd.get("recipient_uei") or "").strip().upper()
        agency = (sd.get("awarding_agency") or "").strip()
        recipient = uei_to_entity.get(uei)
        if not recipient or not agency:
            continue
        award = agg.setdefault((agency, recipient), Award())
        award.total_usd += _to_float(sd.get("amount_usd"))
        award.award_count += 1
        date = sd.get("start_date")
        if date and (award.last_award is None or date > award.last_award):
            award.last_award = date
    return agg


# ── DB layer ──────────────────────────────────────────────────────────────────────────────────

async def _get_or_create_agency(conn, name: str, cache: dict[str, str]) -> str:
    """Idempotent get-or-create of a ``gov_agency`` entity by canonical name (cached per run)."""
    if name in cache:
        return cache[name]
    row = await conn.fetchrow(
        "SELECT id::text AS id FROM entities WHERE canonical_name = $1 AND entity_type = 'gov_agency' LIMIT 1",
        name,
    )
    if row is None:
        row = await conn.fetchrow(
            "INSERT INTO entities (canonical_name, entity_type, desk) VALUES ($1, 'gov_agency', '{}') "
            "RETURNING id::text AS id",
            name,
        )
    cache[name] = row["id"]
    return row["id"]


async def _uei_index(conn) -> dict[str, str]:
    rows = await conn.fetch(
        "SELECT id_value AS uei, entity_id::text AS entity_id FROM entity_identifiers "
        "WHERE id_type = 'uei' AND valid_to IS NULL"
    )
    return {r["uei"].upper(): r["entity_id"] for r in rows}


async def build_funding_edges(conn) -> dict:
    """Recompute AWARDED (agency → recipient) edges from USAspending. Idempotent; returns a summary."""
    now = datetime.now(timezone.utc)
    uei_map = await _uei_index(conn)
    rows = await conn.fetch(
        "SELECT structured_data FROM normalized_records WHERE source_id = 'usaspending'"
    )
    records = []
    for r in rows:
        sd = r["structured_data"]
        records.append(json.loads(sd) if isinstance(sd, str) else (sd or {}))

    agg = aggregate_awards(records, uei_map)

    cache: dict[str, str] = {}
    desired: set[tuple[str, str]] = set()
    for (agency, recipient), award in agg.items():
        agency_id = await _get_or_create_agency(conn, agency, cache)
        desired.add((agency_id, recipient))
        props = json.dumps({
            "total_usd": round(award.total_usd, 2),
            "award_count": award.award_count,
            "agency": agency,
            "last_award": award.last_award,
        })
        await conn.execute(
            "INSERT INTO entity_edges "
            "  (from_entity_id, to_entity_id, edge_type, properties, confidence, valid_from) "
            "VALUES ($1::uuid, $2::uuid, 'AWARDED', $3::jsonb, 1.0, $4) "
            "ON CONFLICT (from_entity_id, to_entity_id, edge_type) WHERE valid_to IS NULL "
            "DO UPDATE SET properties = EXCLUDED.properties, transaction_time = now()",
            agency_id, recipient, props, now,
        )

    live = await conn.fetch(
        "SELECT from_entity_id::text AS f, to_entity_id::text AS t FROM entity_edges "
        "WHERE edge_type = 'AWARDED' AND valid_to IS NULL"
    )
    retired = 0
    for r in live:
        if (r["f"], r["t"]) not in desired:
            await conn.execute(
                "UPDATE entity_edges SET valid_to = $3, transaction_time = now() "
                "WHERE from_entity_id = $1::uuid AND to_entity_id = $2::uuid "
                "AND edge_type = 'AWARDED' AND valid_to IS NULL",
                r["f"], r["t"], now,
            )
            retired += 1
    return {"agencies": len(cache), "awarded_edges": len(desired), "retired": retired}
