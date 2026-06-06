import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

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
) -> list[tuple[dict, float]]:
    scorer = MaterialityScorer(
        source_weights=json.loads(settings.source_weights),
        entity_importance=json.loads(settings.entity_importance),
        materiality_threshold=settings.materiality_threshold,
        magnitude_min_window=settings.magnitude_min_window,
        window_amounts=[],
    )

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                nr.id, nr.source_id, nr.structured_data, nr.entity_mentions,
                nr.created_at, rr.id AS rr_id
            FROM normalized_records nr
            JOIN raw_records rr ON rr.id = nr.raw_record_id
            WHERE nr.created_at >= $1
            """,
            since,
        )

        # Fetch window amounts for min-max normalization (D035)
        amount_rows = await conn.fetch(
            """
            SELECT (structured_data->>'amount_usd')::float AS amount
            FROM normalized_records
            WHERE created_at >= now() - INTERVAL '90 days'
              AND structured_data->>'amount_usd' IS NOT NULL
            """
        )

    scorer.window_amounts = [r["amount"] for r in amount_rows if r["amount"]]

    scored = []
    for row in rows:
        sd = row["structured_data"] or {}
        mentions = row["entity_mentions"] or []
        primary_mention = mentions[0] if mentions else {}
        entity_type = primary_mention.get("entity_type", "company")
        amount_usd = sd.get("amount_usd")

        # Corroboration: count records sharing normalized_mention (D036)
        primary_name = primary_mention.get("normalized", "")
        corroboration = sum(
            1 for r2 in rows
            if r2["id"] != row["id"]
            and any(
                m.get("normalized") == primary_name
                for m in (r2["entity_mentions"] or [])
                if primary_name
            )
        )

        score = scorer.score(
            source_id=row["source_id"],
            is_new=True,
            amount_usd=amount_usd,
            entity_type=entity_type,
            corroboration_count=corroboration,
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

    # Step 3: Build query vector from top-5 seed records
    query_vector = await build_query_vector(pool, since, top_k_seed=5)
    if query_vector is None:
        raise RuntimeError("No embedded records in window — cannot build query vector")

    # Step 4: Retrieve top-K passages (immutable PassageContext list, D041)
    passages = await fetch_passages(
        pool, query_vector, since, top_k=settings.rag_passage_top_k
    )
    log.info("passages_retrieved", count=len(passages))

    # Step 5: Materiality scoring → candidate filter
    candidates = await _score_candidates(pool, since)
    if len(candidates) < settings.brief_min_items:
        raise RuntimeError(
            f"Only {len(candidates)} material candidates — below BRIEF_MIN_ITEMS={settings.brief_min_items}"
        )

    # Step 6: Build verified facts from material candidates
    verified_facts = [
        {
            "record_id": str(c["rr_id"]),
            "source_id": c["source_id"],
            "data": c["structured_data"],
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
    )

    parsed = parse_json(content)
    if parsed is None:
        raise RuntimeError("Synthesis output was not valid JSON after retries")

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
        items=parsed.get("items", []),
        passages=passages,
        synthesis_model=synthesis_model,
        model_waterfall_metadata=metadata,
    )


async def persist_brief(
    brief: GeneratedBrief,
    desk: str,
    brief_date: str,
    faithfulness_score: float,
    eval_passed: bool,
    excluded_item_ids: set[str],
    pool: asyncpg.Pool,
) -> str:
    brief_id = str(uuid.uuid4())
    status = "published" if eval_passed else "failed"
    published_at = datetime.now(timezone.utc) if eval_passed else None

    surviving_items = [
        item for item in brief.items
        if item.get("_item_id") not in excluded_item_ids
    ]

    async with pool.acquire() as conn:
        async with conn.transaction():
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
                    "{}",
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
