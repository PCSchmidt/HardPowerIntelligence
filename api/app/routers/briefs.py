"""Brief endpoints: list, latest (with D013 staleness fallback), and by-id (tier-gated)."""
from __future__ import annotations

import json
from datetime import date, timedelta
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.deps import Principal, get_pool, get_principal
from app.errors import APIError
from app.routers.entities import entities_for_ids

router = APIRouter()

_VALID_DESKS = {"defense", "energy", "ai"}
_ARCHIVE_DAYS = 90


def _validate_desk(desk: str) -> None:
    if desk not in _VALID_DESKS:
        raise APIError(400, "bad_request", f"Unknown desk '{desk}'")


def _parse_signal_series(brief: asyncpg.Record) -> dict | None:
    """Brief Signal sparkline payload (D089). JSONB comes back from asyncpg as a JSON string
    (no codec registered), so parse it; tolerate a dict too. Absent column (pre-migration) or
    empty → None, so the reader simply renders no sparkline."""
    raw = brief["signal_series"] if "signal_series" in brief else None
    if not raw:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def _latest_available_indicator(brief: asyncpg.Record | dict, today: date) -> dict | None:
    """A neutral "this is the latest available brief, not necessarily today's" note for a quiet
    day (a desk cleanly skipped, D085) or a pre-cron page load. Distinct from the D013
    pending/failed staleness, which is an alarming "generation broke" case — here nothing is
    wrong, the day was just quiet, so the reader shouldn't see yesterday's date with no context.
    Returns None when the served brief IS today's, so a normal day shows no banner."""
    if brief["date"] >= today:
        return None
    return {
        "current_status": "latest_available",
        "last_updated": brief["published_at"],
        "message": "You're viewing the most recent brief — a fresh brief publishes each weekday morning.",
    }


async def _assemble_brief(conn: asyncpg.Connection, brief: asyncpg.Record, staleness: dict | None = None) -> dict:
    items = await conn.fetch(
        """
        SELECT id, item_type, headline, body, read, watch,
               attribution, entity_ids, materiality_score, display_order
        FROM brief_items WHERE brief_id = $1 ORDER BY display_order
        """,
        brief["id"],
    )
    citations = await conn.fetch(
        """
        SELECT id, brief_item_id, source_id, url, fetched_at, native_id,
               license_class, title, excerpt
        FROM citations WHERE brief_id = $1
        """,
        brief["id"],
    )

    # item_10: build citation_ids per item by JOINing citations on brief_item_id
    cit_ids_by_item: dict[str, list[str]] = {}
    for c in citations:
        if c["brief_item_id"] is not None:
            cit_ids_by_item.setdefault(str(c["brief_item_id"]), []).append(str(c["id"]))

    # Entity chips (T3.4, D091): resolve every entity_id referenced by the items to a display
    # summary in one batched query, so the reader renders chips without an N+1. Empty when the
    # graph isn't populated yet — the reader simply shows no chips.
    entity_ids = list({e for it in items for e in (it["entity_ids"] or [])})
    entities = await entities_for_ids(conn, entity_ids)

    return {
        "id": str(brief["id"]),
        "desk": brief["desk"],
        "date": brief["date"],
        "status": brief["status"],
        "published_at": brief["published_at"],
        "headline": brief["headline"],
        "bluf": brief["bluf"],
        "faithfulness_score": brief["faithfulness_score"],
        # Cross-signal analysis thesis (D071/D073); grounded gate applied at persist.
        "convergence_read": brief["convergence_read"],
        # GDELT media-attention momentum (D082): labeled aggregate color, not a cited fact.
        "signal": brief["signal"] if "signal" in brief else "",
        # Lead-theme volume series for the Signal sparkline (D089); None if none.
        "signal_series": _parse_signal_series(brief),
        "staleness_indicator": staleness,
        # Resolved entity chips keyed by id (T3.4, D091); reader maps item.entity_ids → these.
        "entities": entities,
        "items": [
            {
                "id": str(it["id"]),
                "item_type": it["item_type"],
                "headline": it["headline"],
                "body": it["body"],
                # Analysis layer (D071/D073): grounded interpretation, "" if withheld.
                "read": it["read"],
                "watch": it["watch"],
                # Epistemic attribution (D098/D099): the item's confidence/basis label —
                # confirmed / reported / analysis / speculative. The reader renders it as
                # a chip; grounding is shown as transparency, never used to suppress.
                "attribution": it["attribution"],
                "entity_ids": [str(e) for e in (it["entity_ids"] or [])],
                "citation_ids": cit_ids_by_item.get(str(it["id"]), []),
                "materiality_score": it["materiality_score"],
                "display_order": it["display_order"],
            }
            for it in items
        ],
        "citations": [
            {
                "id": str(c["id"]),
                "source_id": c["source_id"],
                "url": c["url"],
                "fetched_at": c["fetched_at"],
                "native_id": c["native_id"],
                "license_class": c["license_class"],
                "title": c["title"],
                "excerpt": c["excerpt"],
            }
            for c in citations
        ],
        "sources_missing": list(brief["sources_missing"] or []),
        "model_waterfall": {
            "synthesis_model": brief["synthesis_model"],
            "eval_model": brief["eval_model"],
            "eval_passed": brief["eval_passed"],
        },
    }


@router.get("/briefs")
async def list_briefs(
    desk: str = Query(...),
    limit: int = Query(20, ge=1, le=50),
    principal: Principal = Depends(get_principal),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    _validate_desk(desk)
    # Free: current day only. Pro: rolling 90-day archive.
    floor = date.today() if principal.tier == "free" else date.today() - timedelta(days=_ARCHIVE_DAYS)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, desk, date, status, published_at, headline, bluf, faithfulness_score
            FROM briefs
            WHERE desk = $1 AND status = 'published' AND date >= $2
            ORDER BY date DESC LIMIT $3
            """,
            desk, floor, limit,
        )
    return {
        "briefs": [
            {
                "id": str(r["id"]),
                "desk": r["desk"],
                "date": r["date"],
                "status": r["status"],
                "published_at": r["published_at"],
                "headline": r["headline"],
                "bluf": r["bluf"],
                "faithfulness_score": r["faithfulness_score"],
            }
            for r in rows
        ],
        "next_cursor": None,
    }


@router.get("/briefs/latest")
async def latest_brief(
    desk: str = Query(...),
    principal: Principal = Depends(get_principal),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    _validate_desk(desk)
    async with pool.acquire() as conn:
        newest = await conn.fetchrow(
            "SELECT * FROM briefs WHERE desk = $1 ORDER BY date DESC, created_at DESC LIMIT 1",
            desk,
        )
        if newest is not None and newest["status"] == "published":
            return await _assemble_brief(conn, newest, _latest_available_indicator(newest, date.today()))

        # D013 fallback: newest is pending/failed (or none) — serve last published + staleness
        last_published = await conn.fetchrow(
            "SELECT * FROM briefs WHERE desk = $1 AND status = 'published' "
            "ORDER BY published_at DESC LIMIT 1",
            desk,
        )
        if last_published is None:
            raise APIError(404, "not_found", "No published brief available for this desk")

        staleness = None
        if newest is not None and newest["status"] in ("pending", "failed"):
            message = (
                "Today's brief is being generated. Showing last published brief."
                if newest["status"] == "pending"
                else "Today's brief failed generation. Showing last published brief."
            )
            staleness = {
                "last_updated": last_published["published_at"],
                "current_status": newest["status"],
                "message": message,
            }
        return await _assemble_brief(conn, last_published, staleness)


@router.get("/wire/latest")
async def latest_wire(
    desk: str = Query(...),
    principal: Principal = Depends(get_principal),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    """The desk's "Full Wire" (D112): material, on-thesis items that cleared scoring but
    lost the brief's space cut — title + source + link, no narrative — so nothing relevant
    is thrown away on a heavy news day. Tied to the desk's latest PUBLISHED brief; same
    free-tier access as that brief (the current desk read), so any signed-in user sees it."""
    _validate_desk(desk)
    async with pool.acquire() as conn:
        brief = await conn.fetchrow(
            "SELECT id, desk, date, published_at FROM briefs "
            "WHERE desk = $1 AND status = 'published' ORDER BY published_at DESC LIMIT 1",
            desk,
        )
        if brief is None:
            raise APIError(404, "not_found", "No published brief available for this desk")

        try:
            rows = await conn.fetch(
                "SELECT source_id, native_id, item_type, headline, url, materiality_score "
                "FROM brief_wire WHERE brief_id = $1 ORDER BY display_order ASC",
                brief["id"],
            )
        except asyncpg.UndefinedTableError:
            # Migration 20260630000001 not yet applied — degrade to an empty wire, never 500.
            rows = []

    return {
        "desk": brief["desk"],
        "brief_id": str(brief["id"]),
        "date": brief["date"],
        "published_at": brief["published_at"],
        "items": [
            {
                "source_id": r["source_id"],
                "native_id": r["native_id"],
                "item_type": r["item_type"],
                "headline": r["headline"],
                "url": r["url"],
                "materiality_score": r["materiality_score"],
            }
            for r in rows
        ],
    }


@router.get("/briefs/{brief_id}")
async def get_brief(
    brief_id: UUID,
    principal: Principal = Depends(get_principal),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    async with pool.acquire() as conn:
        brief = await conn.fetchrow(
            "SELECT * FROM briefs WHERE id = $1 AND status = 'published'",
            brief_id,
        )
        if brief is None:
            raise APIError(404, "not_found", "Brief not found")

        # Archive gating: any brief older than today requires Pro.
        if brief["date"] < date.today() and principal.tier == "free":
            raise APIError(403, "pro_required", "Pro subscription required for archive access")

        return await _assemble_brief(conn, brief)
