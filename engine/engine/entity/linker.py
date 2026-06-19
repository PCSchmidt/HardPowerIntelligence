"""Wire entity resolution into brief generation (T3.3, D091).

At brief-persist time each ``brief_item`` is linked to the entities it is about, by resolving the
authoritative entity mentions on its source records. Precision-first (the resolver's bar): an exact
identifier (ticker / cik / uei) wins; otherwise the precision-first trigram match; an ambiguous name
is left unlinked rather than risk a wrong ticker.

**Private / venture / government entities** — those with an authoritative identifier (a CIK from an
EDGAR private filer, a UEI from a USAspending recipient) but no public ticker, so absent from the
SEC-seeded reference set — are MINTED here from that identifier. This is how the graph grows past the
public universe (D091); a curated list is never required.

Best-effort by construction: the caller runs this OUTSIDE the brief transaction and swallows errors,
so an unseeded graph or a resolution hiccup can never roll back or dark a cited brief.
"""
from __future__ import annotations

import json

import structlog

from engine.entity.reference import pad_cik
from engine.entity.resolution import resolve_mention
from engine.entity.resolver import normalize_mention

log = structlog.get_logger()

# Identifiers globally unique + authoritative enough to mint a brand-new entity from. (A ticker is
# not here: a ticker we don't already have seeded is suspect, and tickers get reused/delisted.)
_MINTABLE_ID_TYPES = ("cik", "uei")


def _loads(value: object) -> object:
    """asyncpg returns JSONB columns as text (no codec registered) — parse defensively."""
    if isinstance(value, str):
        return json.loads(value)
    return value


def extract_resolution_inputs(
    source_id: str,
    entity_mentions: list[dict] | None,
    structured_data: dict | None,
) -> list[tuple[str, list[tuple[str, str]]]]:
    """Pure: shape a normalized_record's mentions into ``(name, identifiers)`` resolution inputs.

    Identifiers come off the mention dict (EDGAR carries ticker + cik) and, for USAspending, the
    recipient UEI — which lives on ``structured_data`` rather than the mention. CIKs are padded to
    the SEC-canonical 10 digits so they match the seeded identifiers; tickers/UEIs are upper-cased.
    """
    structured_data = structured_data or {}
    out: list[tuple[str, list[tuple[str, str]]]] = []
    for mention in entity_mentions or []:
        name = (mention.get("mention") or "").strip()
        if not name:
            continue
        ids: list[tuple[str, str]] = []
        if mention.get("ticker"):
            ids.append(("ticker", str(mention["ticker"]).strip().upper()))
        if mention.get("cik"):
            ids.append(("cik", pad_cik(mention["cik"])))
        if mention.get("uei"):
            ids.append(("uei", str(mention["uei"]).strip().upper()))
        if source_id == "usaspending" and structured_data.get("recipient_uei"):
            uei = ("uei", str(structured_data["recipient_uei"]).strip().upper())
            if uei not in ids:
                ids.append(uei)
        out.append((name, ids))
    return out


async def _mint_entity(conn, name: str, identifiers: list[tuple[str, str]]) -> str:
    """Create a new entity from authoritative identifier(s) — the private/venture/gov path.

    Idempotent in practice: the caller mints only when ``resolve_mention`` found no identifier match,
    and each mint commits before the next mention resolves, so a recipient seen twice resolves to the
    entity minted the first time.
    """
    async with conn.transaction():
        row = await conn.fetchrow(
            "INSERT INTO entities (canonical_name, entity_type, desk) "
            "VALUES ($1, 'company', '{}'::text[]) RETURNING id::text AS id",
            name,
        )
        entity_id = row["id"]
        for id_type, id_value in identifiers:
            await conn.execute(
                "INSERT INTO entity_identifiers (entity_id, id_type, id_value, source, valid_from) "
                "VALUES ($1::uuid, $2, $3, 'brief_resolution', now())",
                entity_id, id_type, id_value,
            )
        await conn.execute(
            "INSERT INTO entity_aliases (entity_id, alias, alias_normalized, source) "
            "VALUES ($1::uuid, $2, $3, 'brief_resolution') "
            "ON CONFLICT (entity_id, alias_normalized) DO NOTHING",
            entity_id, name, normalize_mention(name),
        )
    return entity_id


async def resolve_item_entities(conn, raw_record_ids: list[str]) -> list[str]:
    """Resolve (and, where authoritative, mint) the entities behind one brief item's source records.

    Returns a de-duplicated, order-preserving list of ``entities.id`` strings.
    """
    if not raw_record_ids:
        return []
    rows = await conn.fetch(
        "SELECT source_id, entity_mentions, structured_data FROM normalized_records "
        "WHERE raw_record_id = ANY($1::uuid[])",
        raw_record_ids,
    )
    entity_ids: list[str] = []
    seen: set[str] = set()
    for row in rows:
        mentions = _loads(row["entity_mentions"]) or []
        structured = _loads(row["structured_data"]) or {}
        for name, identifiers in extract_resolution_inputs(row["source_id"], mentions, structured):
            result = await resolve_mention(conn, name, identifiers=identifiers)
            entity_id = result.entity_id
            if entity_id is None:
                mintable = [(t, v) for (t, v) in identifiers if t in _MINTABLE_ID_TYPES and v]
                if mintable:
                    entity_id = await _mint_entity(conn, name, mintable)
            if entity_id and entity_id not in seen:
                seen.add(entity_id)
                entity_ids.append(entity_id)
    return entity_ids
