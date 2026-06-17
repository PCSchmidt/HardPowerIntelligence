import json
import uuid
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone

import asyncpg
import structlog

from engine.brief.materiality import MaterialityScorer
from engine.brief.prompt import build_synthesis_prompt
from engine.brief.rag import (
    PassageContext,
    build_query_vector,
    embed_pending_records,
    fetch_passages,
)
from engine.brief.significance import filter_significant
from engine.db import transient_retry
from engine.eval.citation_eval import extract_citation_indices, strip_uncited_sentences
from engine.llm.client import llm_client, parse_json
from engine.settings import settings

log = structlog.get_logger()


@dataclass
class GeneratedBrief:
    headline: str
    bluf: str
    items: list[dict]
    passages: list[PassageContext]
    synthesis_model: str
    model_waterfall_metadata: dict = field(default_factory=dict)
    convergence_read: str = ""   # cross-signal analysis thesis (D071); "" if none
    signal: str = ""             # labeled GDELT media-attention momentum (D082); "" if none


async def _get_window_start(pool: asyncpg.Pool) -> datetime:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT generation_started_at FROM briefs "
            "WHERE status = 'published' ORDER BY published_at DESC LIMIT 1"
        )
    if row and row["generation_started_at"]:
        return row["generation_started_at"]
    fallback = timedelta(hours=settings.brief_window_hours_fallback)
    return datetime.now(timezone.utc) - fallback


async def _score_candidates(
    pool: asyncpg.Pool,
    since: datetime,
    desk: str,
) -> list[tuple[dict, float]]:
    scorer = MaterialityScorer(
        source_weights=json.loads(settings.source_weights),
        entity_importance=json.loads(settings.entity_importance),
        materiality_threshold=settings.materiality_threshold,
        magnitude_min_window=settings.magnitude_min_window,
        window_amounts=[],
        cross_sector_weight=settings.materiality_cross_sector_weight,
    )

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                nr.id, nr.source_id, nr.record_type, nr.structured_data,
                nr.entity_mentions, nr.text_chunk, nr.desk, nr.created_at,
                rr.id AS rr_id, rr.url, rr.native_id, rr.fetched_at
            FROM normalized_records nr
            JOIN raw_records rr ON rr.id = nr.raw_record_id
            WHERE nr.created_at >= $1
              AND $2 = ANY(nr.desk)
            """,
            since,
            desk,
        )

        # Fetch window amounts for min-max normalization within the desk (D035)
        amount_rows = await conn.fetch(
            """
            SELECT (structured_data->>'amount_usd')::float AS amount
            FROM normalized_records
            WHERE created_at >= now() - INTERVAL '90 days'
              AND $1 = ANY(desk)
              AND structured_data->>'amount_usd' IS NOT NULL
            """,
            desk,
        )

    scorer.window_amounts = [r["amount"] for r in amount_rows if r["amount"]]

    # Pre-parse all JSONB fields (asyncpg may return them as raw strings)
    def _parse_json_field(val):
        if isinstance(val, str):
            return json.loads(val)
        return val or {}

    def _parse_json_list(val):
        if isinstance(val, str):
            return json.loads(val)
        return val or []

    parsed_rows = [
        {
            **dict(row),
            "_sd": _parse_json_field(row["structured_data"]),
            "_em": _parse_json_list(row["entity_mentions"]),
        }
        for row in rows
    ]

    scored = []
    for row in parsed_rows:
        sd = row["_sd"]
        mentions = row["_em"]
        primary_mention = mentions[0] if mentions else {}
        entity_type = primary_mention.get("entity_type", "company")
        amount_usd = sd.get("amount_usd")

        # Corroboration: count records sharing normalized_mention (D036)
        primary_name = primary_mention.get("normalized", "")
        corroboration = sum(
            1 for r2 in parsed_rows
            if r2["id"] != row["id"]
            and primary_name
            and any(
                m.get("normalized") == primary_name
                for m in r2["_em"]
            )
        )

        desk_count = len(row.get("desk") or [])
        score = scorer.score(
            source_id=row["source_id"],
            is_new=True,
            amount_usd=amount_usd,
            entity_type=entity_type,
            corroboration_count=corroboration,
            desk_count=desk_count,
        )
        if scorer.is_material(score):
            scored.append((dict(row), score))

    return sorted(scored, key=lambda x: x[1], reverse=True)


def _novelty_key(row: dict) -> str:
    """Stable identity for anti-rehash dedup: source + external native id (D074).

    native_id (e.g. an award number or 8-K accession) is stable across re-ingestion,
    unlike raw_record_id, so a long-lived item is recognized even if re-fetched."""
    return f"{row.get('source_id', '')}:{row.get('native_id', '')}"


async def _recently_featured(pool: asyncpg.Pool, desk: str, window_days: int) -> set[str]:
    """``_novelty_key`` set for records cited in this desk's PUBLISHED briefs within the
    last ``window_days`` (D074). Only published briefs count — a failed/superseded brief
    never reached a reader, so its items aren't "already covered"."""
    if window_days <= 0:
        return set()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT c.source_id, c.native_id
            FROM citations c
            JOIN briefs b ON b.id = c.brief_id
            WHERE b.desk = $1 AND b.status = 'published' AND b.date >= $2
            """,
            desk,
            date.today() - timedelta(days=window_days),
        )
    return {f"{r['source_id']}:{r['native_id']}" for r in rows}


def apply_novelty_penalty(
    candidates: list[tuple[dict, float]],
    featured_keys: set[str],
    penalty: float,
) -> list[tuple[dict, float]]:
    """Down-rank recently-featured records, then re-sort by adjusted score (D074).

    Multiplies the materiality score of any candidate already featured in a recent
    published brief by ``penalty`` (<1), so fresh items lead. It demotes rather than
    drops, so a long-lived item still re-leads when nothing fresher is material —
    keeping the brief honest (no rehash) without ever forcing it empty."""
    if not featured_keys or penalty >= 1.0:
        return candidates
    adjusted = [
        (row, score * penalty if _novelty_key(row) in featured_keys else score)
        for row, score in candidates
    ]
    return sorted(adjusted, key=lambda x: x[1], reverse=True)


def _select_facts(
    candidates: list[tuple[dict, float]],
    limit: int,
    advancement_floor: int,
) -> list[tuple[dict, float]]:
    """Choose the fact set for synthesis: top candidates by materiality, but reserve
    up to ``advancement_floor`` slots for advancement records (``research_paper``) so a
    high-$ capital desk doesn't crowd out the technology-advancement leg (D063/D068).
    Output preserves materiality order. ``candidates`` is assumed materiality-sorted."""
    adv = [c for c in candidates if c[0].get("record_type") == "research_paper"]
    cap = [c for c in candidates if c[0].get("record_type") != "research_paper"]
    n_adv = min(max(advancement_floor, 0), len(adv), limit)
    chosen = adv[:n_adv] + cap[: limit - n_adv]
    if len(chosen) < limit:                       # not enough capital — top up with adv
        chosen = (chosen + adv[n_adv:])[:limit]
    chosen_ids = {str(c[0]["rr_id"]) for c in chosen}
    return [c for c in candidates if str(c[0]["rr_id"]) in chosen_ids]


def _candidate_passages(facts: list[tuple[dict, float]]) -> list[PassageContext]:
    """Build citable passages straight from the material facts, so every fact the
    synthesis is told to prioritize has a passage to cite (D068). The index is a
    placeholder here; ``_merge_passages`` assigns the final 1-based [CITE:N] index."""
    return [
        PassageContext(
            index=0,
            raw_record_id=str(c["rr_id"]),
            source_id=c["source_id"],
            url=c.get("url") or "",
            fetched_at=c["fetched_at"],
            native_id=c.get("native_id") or "",
            excerpt=c.get("text_chunk") or "",
        )
        for c, _ in facts
    ]


def _merge_passages(
    fact_passages: list[PassageContext],
    rag_passages: list[PassageContext],
    cap: int,
) -> list[PassageContext]:
    """Union fact passages (material, always citable) with RAG context passages,
    dedup by ``raw_record_id`` (fact passages win and keep the lower indices), then
    re-index 1..N contiguously so [CITE:N] maps correctly (D068)."""
    seen: set[str] = set()
    merged: list[PassageContext] = []
    for p in [*fact_passages, *rag_passages]:
        if p.raw_record_id in seen:
            continue
        seen.add(p.raw_record_id)
        merged.append(p)
        if len(merged) >= cap:
            break
    return [replace(p, index=i + 1) for i, p in enumerate(merged)]


async def generate_brief(desk: str, pool: asyncpg.Pool) -> GeneratedBrief:
    started_at = datetime.now(timezone.utc)

    # Step 1: Determine time window
    since = await _get_window_start(pool)
    log.info("brief_window", desk=desk, since=since.isoformat())

    # Step 2: Embed any un-embedded records in the window (D034)
    embedded = await embed_pending_records(pool, since)
    log.info("embeddings_bootstrapped", count=embedded)

    # Step 3: Materiality scoring → candidate filter (desk-scoped, convergence-boosted).
    # Done first so retrieval can be seeded by the most material records and the
    # citation pool can be aligned to the facts we actually write about (D068).
    candidates = await _score_candidates(pool, since, desk)
    # Anti-rehash (D074): down-rank records already featured in recent published briefs
    # so a long-lived item (e.g. a multi-year award) doesn't lead the brief day after day.
    featured = await _recently_featured(pool, desk, settings.novelty_window_days)
    candidates = apply_novelty_penalty(candidates, featured, settings.novelty_penalty)
    log.info("novelty_applied", desk=desk, featured_records=len(featured))
    if len(candidates) < settings.brief_min_items:
        raise RuntimeError(
            f"Only {len(candidates)} material candidates — below BRIEF_MIN_ITEMS={settings.brief_min_items}"
        )

    # Step 4: Choose the fact set — top by materiality, with an advancement floor so
    # capital flow doesn't crowd out the technology leg (D063/D068).
    facts = _select_facts(
        candidates, settings.brief_max_items * 2, settings.brief_advancement_floor
    )

    # Step 4b: Significance gate (D085) — drop true-but-trivial items (routine commodity
    # procurement, filings with no material event, stale actions) so the brief isn't
    # padded with filler. Fail-open and never empties; the publish gate handles thin days.
    facts, dropped = await filter_significant(facts, desk)
    if dropped:
        log.info(
            "significance_filtered", desk=desk, kept=len(facts), dropped=len(dropped),
            reasons=[r for _d, _s, r in dropped][:8],
        )

    # Step 5: Build the citation pool. Fact passages (built straight from the facts)
    # are ALWAYS citable; RAG passages add semantic context, seeded by the material
    # facts so a high-volume source can't hijack retrieval by recency (D068, D041).
    fact_passages = _candidate_passages(facts)
    query_vector = await build_query_vector(
        pool, since, desk, seed_texts=[c.get("text_chunk") or "" for c, _ in facts]
    )
    rag_passages = (
        await fetch_passages(pool, query_vector, since, settings.rag_passage_top_k, desk)
        if query_vector is not None else []
    )
    passages = _merge_passages(
        fact_passages, rag_passages,
        cap=settings.brief_max_items * 2 + settings.rag_passage_top_k,
    )
    log.info(
        "passages_retrieved", count=len(passages), desk=desk,
        facts=len(fact_passages), rag=len(rag_passages),
    )

    # Step 6: Build verified facts (each has a citable passage by construction, D068)
    verified_facts = [
        {
            "record_id": str(c["rr_id"]),
            "source_id": c["source_id"],
            "data": json.loads(c["structured_data"]) if isinstance(c["structured_data"], str) else (c["structured_data"] or {}),
        }
        for c, _ in facts
    ]

    # Step 7: Synthesis LLM call (D028, D037)
    messages = build_synthesis_prompt(
        desk=desk,
        passages=passages,
        verified_facts=verified_facts,
        max_items=settings.brief_max_items,
    )
    synthesis_model = settings.llm_model_synthesis
    content = await llm_client.complete(
        model=synthesis_model,
        messages=messages,
        json_mode=True,
        fallbacks=[settings.llm_model_synthesis_fallback],
        temperature=settings.llm_temperature,
    )

    parsed = parse_json(content)
    if parsed is None:
        raise RuntimeError("Synthesis output was not valid JSON after retries")

    # Enforce the citation invariant: drop any sentence without a [CITE:N] and
    # re-derive citation indices from the cleaned body, so the published brief
    # contains only provable claims (D058). Items left empty are dropped.
    items = []
    for item in parsed.get("items", []):
        cleaned = strip_uncited_sentences(item.get("body", ""))
        if not cleaned:
            continue
        item["body"] = cleaned
        item["citation_indices"] = extract_citation_indices(cleaned)
        items.append(item)

    metadata = {
        "synthesis_model": synthesis_model,
        "window_start": since.isoformat(),
        "passages_count": len(passages),
        "candidates_count": len(candidates),
        "generation_started_at": started_at.isoformat(),
    }

    return GeneratedBrief(
        headline=parsed.get("headline", ""),
        bluf=parsed.get("bluf", ""),
        items=items,
        passages=passages,
        synthesis_model=synthesis_model,
        model_waterfall_metadata=metadata,
        convergence_read=parsed.get("convergence_read", "") or "",
    )


@transient_retry()
async def persist_brief(
    brief: GeneratedBrief,
    desk: str,
    brief_date: str | date,
    faithfulness_score: float,
    eval_passed: bool,
    excluded_item_ids: set[str],
    pool: asyncpg.Pool,
) -> str:
    brief_id = str(uuid.uuid4())
    if isinstance(brief_date, str):
        brief_date = date.fromisoformat(brief_date)
    status = "published" if eval_passed else "failed"
    published_at = datetime.now(timezone.utc) if eval_passed else None

    surviving_items = [
        item for item in brief.items
        if item.get("_item_id") not in excluded_item_ids
    ]

    async with pool.acquire() as conn:
        async with conn.transaction():
            # Idempotent on (desk, date): replace any existing brief for the day
            # (cascades to brief_items + citations) so re-runs don't UniqueViolation
            # and a failed brief can be superseded by a passing one (D058).
            await conn.execute(
                "DELETE FROM briefs WHERE desk = $1 AND date = $2", desk, brief_date
            )
            await conn.execute(
                """
                INSERT INTO briefs (
                    id, desk, date, status, headline, bluf, convergence_read,
                    faithfulness_score, eval_passed, published_at,
                    synthesis_model, model_waterfall_metadata, signal
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                """,
                brief_id, desk, brief_date, status,
                brief.headline, brief.bluf, brief.convergence_read,
                faithfulness_score, eval_passed, published_at,
                brief.synthesis_model,
                json.dumps(brief.model_waterfall_metadata),
                brief.signal,
            )

            for i, item in enumerate(surviving_items):
                item_id = str(uuid.uuid4())
                await conn.execute(
                    """
                    INSERT INTO brief_items (
                        id, brief_id, item_type, headline, body, read, watch,
                        entity_ids, display_order
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                    """,
                    item_id, brief_id,
                    item.get("item_type", "signal"),
                    item.get("headline", ""),
                    item.get("body", ""),
                    item.get("read", ""),    # analysis layer, grounded gate applied (D073)
                    item.get("watch", ""),
                    [],   # entity_ids resolved in Gate 6 after entity graph is seeded
                    i,
                )

                for idx in item.get("citation_indices", []):
                    passage = next(
                        (p for p in brief.passages if p.index == idx), None
                    )
                    if passage is None:
                        continue
                    await conn.execute(
                        """
                        INSERT INTO citations (
                            brief_id, brief_item_id, raw_record_id,
                            source_id, url, fetched_at, native_id, license_class
                        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                        """,
                        brief_id, item_id, passage.raw_record_id,
                        passage.source_id, passage.url, passage.fetched_at,
                        passage.native_id, "public_domain",
                    )

    log.info("brief_persisted", brief_id=brief_id, status=status, desk=desk)
    return brief_id
