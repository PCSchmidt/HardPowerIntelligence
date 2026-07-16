import json
import re
import uuid
from collections import Counter
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
    extract_published_at,
    fetch_passages,
)
from engine.brief.significance import filter_significant
from engine.db import transient_retry
from engine.entity.linker import resolve_item_entities
from engine.eval.citation_eval import extract_citation_indices, strip_uncited_sentences
from engine.llm.client import llm_client, parse_json
from engine.settings import settings

log = structlog.get_logger()

# The analysis layer (read / watch / convergence_read) is free-form model output that gets
# no downstream cleaning. Occasionally the synthesis model (or a JSON-mode retry) nests a
# field value inside a JSON object — e.g. {"text": "..."} or {"rewritten": "..."} — and it
# then renders verbatim on the desk page (observed on all three desks, 7/4). This unwraps a
# single stray wrapper so only prose reaches the reader; ordinary prose passes untouched.
_ANALYSIS_WRAPPER_KEYS = (
    "text", "analysis", "read", "watch", "rewritten", "body", "content", "convergence_read",
)


def _unwrap_analysis_field(value: str) -> str:
    """Strip a stray JSON-object wrapper from a free-form analysis field, if present."""
    text = (value or "").strip()
    if not (text.startswith("{") and text.endswith("}")):
        return text
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        return text
    if not isinstance(obj, dict):
        return text
    inner = None
    if len(obj) == 1:
        (inner,) = obj.values()
    else:
        for key in _ANALYSIS_WRAPPER_KEYS:
            if isinstance(obj.get(key), str):
                inner = obj[key]
                break
    if isinstance(inner, str):
        return _unwrap_analysis_field(inner)  # collapse a doubly-wrapped value too
    return text


# The item types the DB CHECK on brief_items.item_type accepts — and, not coincidentally, the
# exact keys of the web's ITEM_ICON / ITEM_LABEL / ITEM_BG / ITEM_TEXT maps, which are
# Record<ItemType, …> and would render `undefined` for an unknown key. The taxonomy was fixed on
# 2026-06-05 when the corpus was EDGAR-only (awards + filings); when the net widened to news,
# arXiv and agency feeds the model began reaching for labels outside it, and D140 coerced them all
# to "signal" to stop persist throwing — which flattened real-world military OPERATIONS and
# RESEARCH / tech milestones into the catch-all (7/15 Defense: 10 of 20 items "signal", incl. the
# lead combat-USV story). D143 promotes those two to first-class types. Keep this set in lockstep
# with the DB CHECK (migration 20260716000001) and the web ItemType union — a value in one but not
# the others is the D140 failure in a new place. A free-text LLM field must never reach either unmapped.
_ITEM_TYPES = frozenset({"award", "filing", "policy", "macro", "signal", "operational", "research"})

# Nearest-fit for the labels the model actually reaches for. Deliberately small: the fallback
# is the real safety net, this map only buys a more accurate chip where the intent is obvious.
_ITEM_TYPE_SYNONYMS = {
    "contract": "award", "procurement": "award", "grant": "award", "obligation": "award",
    "sec": "filing", "disclosure": "filing", "earnings": "filing",
    "regulation": "policy", "legislation": "policy", "rule": "policy", "law": "policy",
    "doctrine": "policy", "strategy": "policy",
    "economic": "macro", "economy": "macro", "market": "macro", "financial": "macro",
    # Real-world actions and events (D143) — a strike, a deployment, a reactor coming online.
    "operation": "operational", "combat": "operational", "military": "operational",
    "deployment": "operational", "exercise": "operational", "strike": "operational",
    "patrol": "operational", "incident": "operational", "launch": "operational",
    # R&D and technology milestones (D143) — arXiv preprints, prototypes, breakthroughs.
    "paper": "research", "study": "research", "arxiv": "research", "preprint": "research",
    "technology": "research", "prototype": "research", "milestone": "research",
    "breakthrough": "research", "development": "research",
    # Genuinely just news / an announcement stays the catch-all.
    "news": "signal", "announcement": "signal", "update": "signal",
}


def normalize_item_type(value: object) -> str:
    """Coerce a synthesis-supplied ``item_type`` to one of the five allowed values (D140).

    Idempotent. An unrecognized label degrades to ``"signal"`` (the catch-all) rather than
    raising: the item's FACTS are already gated and citable, so a mislabeled chip is a
    cosmetic loss, while a rejected INSERT takes the whole desk dark.
    """
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if text in _ITEM_TYPES:
        return text
    if text in _ITEM_TYPE_SYNONYMS:
        return _ITEM_TYPE_SYNONYMS[text]
    # Compound labels ("contract_award", "research_paper", "policy_change") — take the first
    # component that maps, so the obvious intent still lands on the right chip.
    for part in text.split("_"):
        if part in _ITEM_TYPES:
            return part
        if part in _ITEM_TYPE_SYNONYMS:
            return _ITEM_TYPE_SYNONYMS[part]
    return "signal"


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
    signal_series: dict | None = None  # lead-theme volume series for the sparkline (D089); None if none
    # "Full Wire" overflow pool (D112): material, on-thesis candidates (froth excluded) that
    # may not make the published brief. persist_brief subtracts the featured records and
    # writes the remainder to brief_wire. Each is a lightweight dict (see _wire_signal).
    wire: list[dict] = field(default_factory=list)


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


def _is_home_desk(row: dict, desk: str) -> bool:
    """True when ``desk`` is this record's PRIMARY (home) desk.

    A record's ``desk`` array is ordered by primacy (the EDGAR/adapter probes list
    the home desk first, e.g. "hyperscale data center" → (ai, energy) = AI-home),
    so the home desk is ``desk[0]``. Primary-desk routing: a cross-desk record
    surfaces on its home desk ONLY; its other desk tags become a convergence marker
    (the ``desk_count`` materiality boost and the entity-graph chip), never a
    duplicate item on every tagged desk. This is the desk-bleed fix — without it a
    record tagged (ai, energy) printed on both the AI and Energy briefs, making each
    read like an everything-desk."""
    desks = row.get("desk") or []
    return bool(desks) and desks[0] == desk


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
            -- Intentionally ANY, not home-desk-only: the full cross-desk
            -- neighborhood feeds corroboration counting and the amount-window
            -- below. Output is narrowed to the home desk via _is_home_desk
            -- after scoring, so a convergence record still corroborates and
            -- still earns its boost without printing on every tagged desk.
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
        # Primary-desk routing: score using the full cross-desk neighborhood
        # (corroboration, desk_count boost) but only surface the record on its
        # home desk, so cross-desk relevance is a convergence marker not a dup.
        if scorer.is_material(score) and _is_home_desk(row, desk):
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


# Near-duplicate collapse (D135): syndicated wire news — GDELT especially — repeats one story
# across dozens of outlets ("Trump Revives Calls For U.S. Control Of Greenland" landed ~30× on
# 2026-07-09), each a distinct native_id so the ingest-level (source_id, native_id, content_hash)
# dedup can't see it. Collapse candidates whose HEADLINE normalizes identically, keeping the
# highest-scoring copy. Conservative — only exact normalized-title matches collapse, so genuinely
# distinct stories survive. Cleans the wire and stops the significance LLM from re-scoring the
# same headline dozens of times (token waste). Note: normalization keeps digits, so "F - 35" and
# "F - 22" stay distinct; it only strips a trailing "| <station>" tail and non-alphanumerics.
def _norm_title(text: str) -> str:
    stripped = (text or "").strip()
    head = stripped.splitlines()[0] if stripped else ""
    head = head.split("|")[0]  # drop "| News Radio 105.5 WERC"-style syndication tails
    return re.sub(r"[^a-z0-9]+", " ", head.lower()).strip()


def dedupe_by_title(candidates: list[tuple[dict, float]]) -> list[tuple[dict, float]]:
    """Collapse exact normalized-title duplicates, keeping the highest-scoring copy (D135).

    Pure. The surviving representative sits at the first occurrence's position but carries the
    best copy's row + score, so downstream ranking reflects the strongest version. Records with a
    blank/unusable title are never collapsed (kept as-is) — we only merge on a real headline."""
    index: dict[str, int] = {}  # normalized title -> position in `out`
    out: list[tuple[dict, float]] = []
    for row, score in candidates:
        key = _norm_title(row.get("text_chunk") or "")
        if not key:
            out.append((row, score))  # can't identify a headline — never collapse
            continue
        if key in index:
            i = index[key]
            if score > out[i][1]:
                out[i] = (row, score)  # keep the better-scoring copy in full
            continue
        index[key] = len(out)
        out.append((row, score))
    return out


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


def _outlet_key(row: dict) -> str | None:
    """Diversity key: the news OUTLET for feed items; ``None`` for structured sources.

    Awards/filings/research are distinct events, not one outlet's stream — capping them
    would wrongly suppress unrelated records — so only feed outlets are diversity-limited (D124)."""
    if row.get("source_id") != "feeds":
        return None
    sd = row.get("_sd")
    if not isinstance(sd, dict):
        sd = row.get("structured_data") or {}
        if isinstance(sd, str):
            try:
                sd = json.loads(sd)
            except (ValueError, TypeError):
                sd = {}
    outlet = sd.get("outlet") if isinstance(sd, dict) else None
    return outlet or None


def apply_outlet_diversity(
    candidates: list[tuple[dict, float]],
    cap: int,
    penalty: float,
) -> list[tuple[dict, float]]:
    """Down-rank a feed outlet's items beyond the first ``cap``, then re-sort (D124).

    A prolific outlet (a lab's own blog, a high-volume trade feed) can otherwise own a
    large share of a desk brief. Walking candidates in score order, the (cap+1)th and later
    item from the same outlet has its score multiplied by ``penalty`` (<1) so it sinks below
    the selection line and lands in the wire instead. Demotes rather than drops (fail-soft:
    on a thin desk a penalized item can still surface), mirroring ``apply_novelty_penalty``."""
    if cap <= 0 or penalty >= 1.0:
        return candidates
    seen: dict[str, int] = {}
    adjusted: list[tuple[dict, float]] = []
    for row, score in candidates:
        outlet = _outlet_key(row)
        if outlet is None:
            adjusted.append((row, score))
            continue
        n = seen.get(outlet, 0)
        seen[outlet] = n + 1
        adjusted.append((row, score * penalty if n >= cap else score))
    return sorted(adjusted, key=lambda x: x[1], reverse=True)


def _select_facts(
    candidates: list[tuple[dict, float]],
    limit: int,
    advancement_floor: int,
    news_floor: int = 0,
) -> list[tuple[dict, float]]:
    """Choose the fact set for synthesis: top candidates by materiality, but guarantee floors
    so a high-$ AWARD-heavy desk can't crowd out two legs it needs. Reserve up to
    ``advancement_floor`` slots for advancement records (``research_paper``, D063/D068) and up
    to ``news_floor`` slots for attributed news (``source_id == "feeds"``, D136) — then fill the
    remaining slots by overall materiality. The floors only change the outcome when those
    records would otherwise miss the cut (award-heavy Defense); on a news-led desk the feeds
    items already rank in, so reserving them is a no-op. Output preserves materiality order;
    ``candidates`` is assumed materiality-sorted."""
    adv = [c for c in candidates if c[0].get("record_type") == "research_paper"]
    news = [
        c for c in candidates
        if c[0].get("record_type") != "research_paper" and c[0].get("source_id") == "feeds"
    ]
    n_adv = min(max(advancement_floor, 0), len(adv), limit)
    n_news = min(max(news_floor, 0), len(news), max(0, limit - n_adv))
    reserved = (adv[:n_adv] + news[:n_news])[:limit]
    # Fill the remaining slots by overall materiality order (reserved items already counted).
    chosen_ids = {str(c[0]["rr_id"]) for c in reserved}
    for c in candidates:
        if len(chosen_ids) >= limit:
            break
        chosen_ids.add(str(c[0]["rr_id"]))
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
            published_at=extract_published_at(
                c["source_id"], c.get("_sd") if c.get("_sd") is not None else c.get("structured_data")
            ),
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
    # Collapse syndicated near-duplicates (D135) before novelty/diversity/selection + wire, so one
    # story doesn't occupy dozens of wire slots or get scored dozens of times by the significance LLM.
    _pre_dedupe = len(candidates)
    candidates = dedupe_by_title(candidates)
    if _pre_dedupe != len(candidates):
        log.info("title_dedupe", desk=desk, collapsed=_pre_dedupe - len(candidates), kept=len(candidates))
    # Anti-rehash (D074): down-rank records already featured in recent published briefs
    # so a long-lived item (e.g. a multi-year award) doesn't lead the brief day after day.
    featured = await _recently_featured(pool, desk, settings.novelty_window_days)
    candidates = apply_novelty_penalty(candidates, featured, settings.novelty_penalty)
    log.info("novelty_applied", desk=desk, featured_records=len(featured))
    # Outlet diversity (D124): keep one prolific feed (e.g. a lab's own blog) from owning the
    # desk — demote its overflow toward the wire. Before _select_facts so the excess stays in
    # `candidates` (→ wire) rather than being computed as significance-froth and discarded.
    candidates = apply_outlet_diversity(
        candidates, settings.outlet_diversity_cap, settings.outlet_diversity_penalty
    )
    if len(candidates) < settings.brief_min_items:
        raise RuntimeError(
            f"Only {len(candidates)} material candidates — below BRIEF_MIN_ITEMS={settings.brief_min_items}"
        )

    # Step 4: Choose the fact set — top by materiality, with an advancement floor so
    # capital flow doesn't crowd out the technology leg (D063/D068).
    selected = _select_facts(
        candidates, settings.brief_max_items * 2, settings.brief_advancement_floor,
        settings.brief_news_floor,
    )

    # Step 4b: Significance gate (D085) — drop true-but-trivial items (routine commodity
    # procurement, filings with no material event, stale actions) so the brief isn't
    # padded with filler. Fail-open and never empties; the publish gate handles thin days.
    facts, dropped = await filter_significant(selected, desk)
    if dropped:
        log.info(
            "significance_filtered", desk=desk, kept=len(facts), dropped=len(dropped),
            reasons=[r for _d, _s, r in dropped][:8],
        )

    # Step 4c: Build the Full Wire overflow pool (D112) — every material, home-desk
    # candidate the significance gate did NOT reject as froth, ranked by score. This is
    # the supply; persist_brief subtracts whatever the published brief features and writes
    # the remainder, so a heavy news day's overflow stays accessible instead of discarded.
    # Wrapped best-effort: the wire is supplementary and must NEVER dark a brief (D089 posture)
    # — a bug here darkened all three desks on 2026-07-02 (D115).
    try:
        wire_pool = _overflow_wire(candidates, selected, facts)
    except Exception as exc:  # noqa: BLE001 — the wire is supplementary; never dark a brief on it
        log.warning("wire_pool_skipped", desk=desk, error=str(exc))
        wire_pool = []

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
        item["item_type"] = normalize_item_type(item.get("item_type"))  # D140
        item["read"] = _unwrap_analysis_field(item.get("read", ""))
        item["watch"] = _unwrap_analysis_field(item.get("watch", ""))
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
        convergence_read=_unwrap_analysis_field(parsed.get("convergence_read", "") or ""),
        wire=wire_pool,
    )


def _item_raw_record_ids(item: dict, passages: list[PassageContext]) -> list[str]:
    """The source raw_record ids behind a brief item, via its [CITE:N] passage indices."""
    cited = set(item.get("citation_indices", []))
    return [p.raw_record_id for p in passages if p.index in cited and p.raw_record_id]


def _overflow_wire(
    candidates: list[tuple[dict, float]],
    selected: list[tuple[dict, float]],
    facts: list[tuple[dict, float]],
) -> list[dict]:
    """Full Wire supply (D112): material home-desk candidates minus significance froth.

    The significance gate judged only the SELECTED facts, and its ``dropped`` list carries
    item *descriptions* (not records) — so froth is computed by difference: the selected
    records the gate did not keep. ``persist_brief`` later subtracts whatever the published
    brief features. (Computing froth from ``dropped`` directly was the D115 crash: its
    elements are ``(description_str, score, reason)``, not candidate dicts.)"""
    kept_rrids = {str(c["rr_id"]) for c, _ in facts}
    froth_rrids = {
        str(c["rr_id"]) for c, _ in selected if str(c["rr_id"]) not in kept_rrids
    }
    return [
        _wire_signal(row, score)
        for row, score in candidates
        if str(row["rr_id"]) not in froth_rrids
    ]


def _wire_signal(row: dict, score: float) -> dict:
    """A lightweight overflow row for the Full Wire (D112): the facts needed to list a
    dropped material item with no narrative — a title, its source, a link, and the score
    that ranks it. Prefers a structured title, falls back to the attributed text_chunk."""
    sd = row.get("_sd")
    if not isinstance(sd, dict):
        sd = json.loads(sd) if isinstance(sd, str) and sd else {}
    title = (sd.get("title") or sd.get("headline") or row.get("text_chunk") or "").strip()
    return {
        "record_id": str(row["rr_id"]),
        "source_id": row.get("source_id", ""),
        "native_id": row.get("native_id"),
        "item_type": row.get("record_type"),
        "headline": title[:300],
        "url": row.get("url") or "",
        "score": round(float(score), 4),
    }


# Sources whose records are third-party content we may store/cite as title + link only,
# never republish raw (scrape_gray, per DATA_SOURCES.md). Everything else is government /
# regulatory / openly-licensed primary data (public_domain). Drives the citation's
# license_class, which the reader uses to decide full-quote vs link-only rendering.
_SCRAPE_GRAY_SOURCES = frozenset({"gdelt", "feeds"})


def _license_class_for(source_id: str) -> str:
    return "scrape_gray" if source_id in _SCRAPE_GRAY_SOURCES else "public_domain"


def _item_source_id(item: dict, passages: list[PassageContext]) -> str:
    """The dominant source behind a brief item, via its [CITE:N] passages — the input
    to epistemic attribution (D098/D099). Returns the most frequently cited source_id,
    or "" when the item has no resolvable citation (which classifies as ``reported``,
    the honest default — we never grant ``confirmed`` standing without a known source)."""
    cited = set(item.get("citation_indices", []))
    srcs = [p.source_id for p in passages if p.index in cited and p.source_id]
    if not srcs:
        return ""
    return Counter(srcs).most_common(1)[0][0]


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

    # Entity linking (T3.3, D091) — best-effort, BEFORE the brief transaction. Resolving (and
    # minting private/venture) entities is the moat, but it must never roll back or dark a cited
    # brief, so it runs on its own connection and any failure falls back to empty entity_ids.
    item_entity_ids: list[list[str]] = [[] for _ in surviving_items]
    try:
        # Sequential by design: resolution mints/dedupes graph entities, so it must serialize
        # to avoid duplicate-entity races. It's the slowest post-pass (~25s/item) — timed here
        # because it is what blew the energy desk's job cap on 2026-07-04 (see daily-brief.yml).
        entity_started = datetime.now(timezone.utc)
        async with pool.acquire() as conn:
            for i, item in enumerate(surviving_items):
                rrids = _item_raw_record_ids(item, brief.passages)
                item_entity_ids[i] = await resolve_item_entities(conn, rrids)
        linked = sum(1 for ids in item_entity_ids if ids)
        log.info(
            "entities_linked", desk=desk, items=len(surviving_items),
            items_with_entities=linked,
            elapsed_s=round((datetime.now(timezone.utc) - entity_started).total_seconds(), 1),
        )
    except Exception as exc:  # noqa: BLE001 — moat enrichment must never dark a brief
        log.warning("entity_resolution_skipped", desk=desk, error=str(exc))
        item_entity_ids = [[] for _ in surviving_items]

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
                        attribution, entity_ids, display_order
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::uuid[],$10)
                    """,
                    item_id, brief_id,
                    # Coerced again at the DB boundary (D140), not just at parse: this INSERT is
                    # the constraint's edge, and any path that builds items without going through
                    # generate_brief must not be able to violate it.
                    normalize_item_type(item.get("item_type")),
                    item.get("headline", ""),
                    item.get("body", ""),
                    item.get("read", ""),    # analysis layer, grounded gate applied (D073)
                    item.get("watch", ""),
                    # Epistemic attribution (D098/D099): confidence/basis label stamped by
                    # evaluate_brief. Defaults to "confirmed" for any path that didn't classify
                    # (matches the column default; the pre-D099 ledger was all cited-confirmed).
                    item.get("attribution", "confirmed"),
                    item_entity_ids[i],   # resolved + minted entities (T3.3, D091); [] on best-effort miss
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
                            source_id, url, fetched_at, native_id, license_class,
                            published_at
                        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                        """,
                        brief_id, item_id, passage.raw_record_id,
                        passage.source_id, passage.url, passage.fetched_at,
                        passage.native_id, _license_class_for(passage.source_id),
                        passage.published_at,
                    )

        # Best-effort, AFTER the brief commits: the GDELT sparkline series (D082/D089) is
        # decorative and must never dark a brief. Writing it outside the transaction means a
        # missing column (e.g. migration 20260618000001 not yet applied) or any write error
        # is logged and skipped — the cited brief is already safely persisted. Same principle
        # as the signal line (D082) and best-effort analysis grounding (D086).
        if brief.signal_series is not None:
            try:
                await conn.execute(
                    "UPDATE briefs SET signal_series = $1 WHERE id = $2",
                    json.dumps(brief.signal_series), brief_id,
                )
            except Exception as exc:  # noqa: BLE001 — decorative; never fail the brief
                log.warning("signal_series_write_skipped", brief_id=brief_id, error=str(exc))

        # Best-effort, AFTER the brief commits: the Full Wire overflow (D112). Subtract the
        # records the published brief already features (they're on the desk page) from the
        # material pool, rank the remainder by score, and persist as the desk's wire. Same
        # never-dark-a-brief posture as signal_series: a missing brief_wire table (migration
        # not yet applied) or any write error is logged and skipped.
        if brief.wire:
            try:
                featured_rrids = {
                    rrid
                    for item in surviving_items
                    for rrid in _item_raw_record_ids(item, brief.passages)
                }
                overflow = sorted(
                    (s for s in brief.wire if s["record_id"] not in featured_rrids),
                    key=lambda s: s.get("score", 0.0),
                    reverse=True,
                )
                for order, s in enumerate(overflow):
                    await conn.execute(
                        """
                        INSERT INTO brief_wire (
                            brief_id, source_id, native_id, item_type,
                            headline, url, materiality_score, display_order
                        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                        """,
                        brief_id, s["source_id"], s.get("native_id"), s.get("item_type"),
                        s["headline"], s.get("url") or None, s.get("score"), order,
                    )
                log.info("wire_persisted", desk=desk, items=len(overflow))
            except Exception as exc:  # noqa: BLE001 — overflow is additive; never fail the brief
                log.warning("wire_write_skipped", brief_id=brief_id, error=str(exc))

    log.info("brief_persisted", brief_id=brief_id, status=status, desk=desk)
    return brief_id
