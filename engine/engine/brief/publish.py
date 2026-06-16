"""Publish gate with regenerate-on-failure (D072).

The synthesis model (deepseek) is non-deterministic even at temperature 0, so the
same desk on the same data can pass the publish gate one run and fail it the next
(observed: 5 provable claims, then 2, twelve minutes apart). For autonomous daily
publishing that means a desk can silently go dark on an unlucky draw.

This module wraps generate→eval in a small retry loop: regenerate up to
``max_attempts`` times, return the first attempt that clears the claim floor, and
otherwise return the best attempt seen (highest provable-claim count) so the caller
still persists the strongest available brief as ``failed``. Only failing desks pay
the extra synthesis cost; a passing desk returns on attempt 1.
"""
from dataclasses import dataclass

import asyncpg
import structlog

from engine.brief.generator import GeneratedBrief, generate_brief
from engine.eval.citation_eval import (
    CitationEvaluator,
    EvalResult,
    extract_citation_indices,
)
from engine.settings import settings

log = structlog.get_logger()


@dataclass
class BriefAttempt:
    """The outcome of generating and evaluating one brief.

    ``brief.items`` have been mutated in place: surviving items carry the
    citation-trimmed ``body`` (D069), re-derived ``citation_indices``, and an
    ``_item_id`` matching ``item_results``; excluded ids are in ``excluded_ids``.
    """
    brief: GeneratedBrief
    item_results: list[EvalResult]
    excluded_ids: set[str]
    provable_claims: int
    eval_passed: bool

    @property
    def surviving_items(self) -> list[dict]:
        return [
            it for it in self.brief.items
            if it.get("_item_id") not in self.excluded_ids
        ]


async def evaluate_brief(
    brief: GeneratedBrief,
    evaluator: CitationEvaluator,
    min_claims: int,
) -> BriefAttempt:
    """Run the per-item citation eval and decide the publish verdict.

    Surviving items are trimmed to their provable sentences (D069); the gate counts
    provable *claims*, not items, so it is stable to how synthesis packs facts (D070).
    """
    item_results: list[EvalResult] = []
    excluded_ids: set[str] = set()

    for i, item in enumerate(brief.items):
        item_id = f"item-{i}"
        item["_item_id"] = item_id
        result = await evaluator.eval_item(
            item_id=item_id,
            body=item.get("body", ""),
            passages=brief.passages,
        )
        item_results.append(result)
        if result.excluded:
            excluded_ids.add(item_id)
        else:
            item["body"] = result.cleaned_body
            item["citation_indices"] = extract_citation_indices(result.cleaned_body)

    provable_claims = evaluator.provable_claim_count(item_results)
    return BriefAttempt(
        brief=brief,
        item_results=item_results,
        excluded_ids=excluded_ids,
        provable_claims=provable_claims,
        eval_passed=provable_claims >= min_claims,
    )


async def generate_publishable_brief(
    desk: str,
    pool: asyncpg.Pool,
    evaluator: CitationEvaluator,
    *,
    min_claims: int | None = None,
    max_attempts: int | None = None,
) -> BriefAttempt:
    """Generate and evaluate a brief, regenerating on a failed gate (D072).

    Returns the first attempt that clears ``min_claims``; if none do within
    ``max_attempts``, returns the best attempt (most provable claims) so the caller
    can still persist the strongest brief, marked failed.
    """
    min_claims = settings.brief_min_claims if min_claims is None else min_claims
    max_attempts = settings.brief_max_attempts if max_attempts is None else max_attempts
    max_attempts = max(1, max_attempts)

    best: BriefAttempt | None = None
    for attempt in range(1, max_attempts + 1):
        brief = await generate_brief(desk=desk, pool=pool)
        result = await evaluate_brief(brief, evaluator, min_claims)
        log.info(
            "brief_attempt",
            desk=desk,
            attempt=attempt,
            max_attempts=max_attempts,
            provable_claims=result.provable_claims,
            passed=result.eval_passed,
        )
        if result.eval_passed:
            return result
        if best is None or result.provable_claims > best.provable_claims:
            best = result

    assert best is not None  # loop runs at least once (max_attempts >= 1)
    return best
