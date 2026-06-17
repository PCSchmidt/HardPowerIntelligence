"""Brief endpoints: list, latest (with D013 staleness fallback), and by-id (tier-gated)."""
from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.deps import Principal, get_pool, get_principal
from app.errors import APIError

router = APIRouter()

_VALID_DESKS = {"defense", "energy", "ai"}
_ARCHIVE_DAYS = 90


def _validate_desk(desk: str) -> None:
    if desk not in _VALID_DESKS:
        raise APIError(400, "bad_request", f"Unknown desk '{desk}'")


async def _assemble_brief(conn: asyncpg.Connection, brief: asyncpg.Record, staleness: dict | None = None) -> dict:
    items = await conn.fetch(
        """
        SELECT id, item_type, headline, body, read, watch,
               entity_ids, materiality_score, display_order
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
        "staleness_indicator": staleness,
        "items": [
            {
                "id": str(it["id"]),
                "item_type": it["item_type"],
                "headline": it["headline"],
                "body": it["body"],
                # Analysis layer (D071/D073): grounded interpretation, "" if withheld.
                "read": it["read"],
                "watch": it["watch"],
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
            return await _assemble_brief(conn, newest)

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
