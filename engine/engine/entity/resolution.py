"""DB-backed entity resolution (T3.2, D091).

Turns an entity *mention* into a resolved `entities.id`, conservatively. The pure scoring
primitives live in ``resolver.py``; this module adds the production path: candidate lookup
against the seeded reference set (pg_trgm similarity on normalized aliases), a precision-first
decision, and an orchestrator that prefers an exact authoritative identifier when present.

**Precision over recall by design.** A wrong ticker corrupts the provenance trust model, so v1
only auto-links on an exact identifier or a high-confidence single match. The medium/low trigram
bands are *recorded* (their triage status) but left unresolved — LLM disambiguation (the
recall lever) is a later, separately-eval'd addition. Accuracy is gated by ``scripts/eval_resolver.py``
against ``tests/fixtures/entity_golden.json`` (``entity_resolver_min_precision``).
"""
from __future__ import annotations

from dataclasses import dataclass

from engine.entity.resolver import (
    ResolutionResult,
    ResolutionStatus,
    normalize_mention,
    triage,
)
from engine.settings import settings

# Two near-tied strong matches are ambiguous (e.g. a parent and its tracking stock); don't
# auto-link — better an unresolved mention than a confidently wrong one.
_AMBIGUITY_MARGIN = 0.05

# pg_trgm similarity on the normalized alias; the `%` operator pre-filters by the trigram
# threshold, similarity() scores 0..1, e.is_active keeps retired entities out.
_CANDIDATE_SQL = """
SELECT e.id::text AS entity_id,
       e.canonical_name AS canonical_name,
       similarity(a.alias_normalized, $1) AS sim
FROM entity_aliases a
JOIN entities e ON e.id = a.entity_id
WHERE a.alias_normalized % $1 AND e.is_active
ORDER BY sim DESC
LIMIT $2
"""


@dataclass
class Candidate:
    entity_id: str
    canonical_name: str
    similarity: float


def decide(
    candidates: list[Candidate],
    *,
    high: float = 0.92,
    medium: float = 0.70,
    low: float = 0.55,
) -> ResolutionResult:
    """Pure decision over pre-scored candidates (top first). Precision-first:

    - no candidates → dismiss
    - two near-tied high candidates → ambiguous; record LLM_DISAMBIGUATE, do NOT link
    - single high candidate → auto-link
    - medium/low → record the triage status but leave unresolved (no LLM in v1)
    """
    if not candidates:
        return ResolutionResult(ResolutionStatus.AUTO_DISMISS, None, 0.0, None)
    top = candidates[0]
    if (
        len(candidates) >= 2
        and top.similarity >= high
        and top.similarity - candidates[1].similarity < _AMBIGUITY_MARGIN
    ):
        return ResolutionResult(ResolutionStatus.LLM_DISAMBIGUATE, None, top.similarity, None)
    status = triage(top.similarity, top.canonical_name, high, medium, low)
    if status is ResolutionStatus.AUTO_LINK:
        return ResolutionResult(status, top.entity_id, top.similarity, "auto_high_confidence")
    return ResolutionResult(status, None, top.similarity, None)


async def find_by_identifier(conn, id_type: str, id_value: str) -> str | None:
    """Exact, current authoritative identifier (ticker/cik/uei/...) → entity_id, or None."""
    row = await conn.fetchrow(
        "SELECT entity_id::text AS entity_id FROM entity_identifiers "
        "WHERE id_type = $1 AND id_value = $2 AND valid_to IS NULL LIMIT 1",
        id_type,
        id_value,
    )
    return row["entity_id"] if row else None


async def find_candidates(conn, normalized_mention: str, *, limit: int = 5) -> list[Candidate]:
    """Top trigram-similar entities for a normalized mention (best first)."""
    rows = await conn.fetch(_CANDIDATE_SQL, normalized_mention, limit)
    return [
        Candidate(r["entity_id"], r["canonical_name"], float(r["sim"]))
        for r in rows
    ]


async def resolve_mention(
    conn,
    mention: str,
    *,
    identifiers: list[tuple[str, str]] | None = None,
) -> ResolutionResult:
    """Resolve a mention to an entity. Exact authoritative identifier wins (confidence 1.0);
    otherwise fall back to a precision-first trigram match."""
    for id_type, id_value in identifiers or []:
        if not id_value:
            continue
        eid = await find_by_identifier(conn, id_type, id_value)
        if eid:
            return ResolutionResult(ResolutionStatus.AUTO_LINK, eid, 1.0, f"identifier:{id_type}")

    normalized = normalize_mention(mention)
    if not normalized:
        return ResolutionResult(ResolutionStatus.AUTO_DISMISS, None, 0.0, None)
    candidates = await find_candidates(conn, normalized)
    return decide(
        candidates,
        high=settings.entity_resolution_high_threshold,
        medium=settings.entity_resolution_medium_threshold,
        low=settings.entity_resolution_low_threshold,
    )
