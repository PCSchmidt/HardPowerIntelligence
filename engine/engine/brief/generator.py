import json
import uuid
from dataclasses import dataclass, field
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
                nr.id, nr.source_id, nr.structured_data, nr.entity_mentions,
                nr.desk, nr.created_at, rr.id AS rr_id
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


async def generate_brief(desk: str, pool: asyncpg.Pool) -> GeneratedBrief:
    started_at = datetime.now(timezone.utc)

    # Step 1: Determine time window
    since = await _get_window_start(pool)
    log.info("brief_window", desk=desk, since=since.isoformat())

    # Step 2: Embed any un-embedded records in the window (D034)
    embedded = await embed_pending_records(pool, since)
    log.info("embeddings_bootstrapped", count=embedded)

    # Step 3: Build query vector from top-5 seed records (desk-scoped)
    query_vector = await build_query_vector(pool, since, desk, top_k_seed=5)
    if query_vector is None:
        raise RuntimeError(f"No embedded {desk} records in window — cannot build query vector")

    # Step 4: Retrieve top-K passages (immutable PassageContext list, D041)
    passages = await fetch_passages(
        pool, query_vector, since, settings.rag_passage_top_k, desk
    )
    log.info("passages_retrieved", count=len(passages), desk=desk)

    # Step 5: Materiality scoring → candidate filter (desk-scoped, convergence-boosted)
    candidates = await _score_candidates(pool, since, desk)
    if len(candidates) < settings.brief_min_items:
        raise RuntimeError(
            f"Only {len(candidates)} material candidates — below BRIEF_MIN_ITEMS={settings.brief_min_items}"
        )

    # Step 6: Build verified facts from material candidates
    verified_facts = [
        {
            "record_id": str(c["rr_id"]),
            "source_id": c["source_id"],
            "data": json.loads(c["structured_data"]) if isinstance(c["structured_data"], str) else (c["structured_data"] or {}),
        }
        for c, _ in candidates[: settings.brief_max_items * 2]
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
    )


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
                    id, desk, date, status, headline, bluf,
                    faithfulness_score, eval_passed, published_at,
                    synthesis_model, model_waterfall_metadata
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                """,
                brief_id, desk, brief_date, status,
                brief.headline, brief.bluf,
                faithfulness_score, eval_passed, published_at,
                brief.synthesis_model,
                json.dumps(brief.model_waterfall_metadata),
            )

            for i, item in enumerate(surviving_items):
                item_id = str(uuid.uuid4())
                await conn.execute(
                    """
                    INSERT INTO brief_items (
                        id, brief_id, item_type, headline, body,
                        entity_ids, display_order
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7)
                    """,
                    item_id, brief_id,
                    item.get("item_type", "signal"),
                    item.get("headline", ""),
                    item.get("body", ""),
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
