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

from engine.brief.epistemics import classify_item
from engine.brief.generator import GeneratedBrief, _item_source_id, generate_brief
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
    """Run the per-item citation eval, stamp each surviving item's epistemic
    attribution, and decide the publish verdict (the widen-the-net flip, D099).

    Grounding level is no longer a suppression gate (the old D070 provable-claim
    publish floor); it is a per-item confidence **label**. A brief publishes when it
    has at least one honest item; each item is graded confirmed / reported / analysis
    / speculative from its source + citation support (``classify_item``, D098).

    The one hard line stays: an item whose claims have NO source support is still
    excluded (D069) — that is not suppressing signal, it is refusing to dress an
    unsupported guess as a confirmed fact. ``min_claims`` no longer gates publication;
    it is retained only as a quality metric / best-attempt tiebreak for the regen loop.
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
            item["attribution"] = classify_item(
                source_id=_item_source_id(item, brief.passages),
                citation_supported=result.claims_passing > 0,
            ).attribution.value

    surviving = sum(
        1 for it in brief.items if it.get("_item_id") not in excluded_ids
    )
    provable_claims = evaluator.provable_claim_count(item_results)
    return BriefAttempt(
        brief=brief,
        item_results=item_results,
        excluded_ids=excluded_ids,
        provable_claims=provable_claims,
        # Publish on honest content, not on a grounding floor: ≥1 non-fabricated item.
        eval_passed=surviving >= 1,
    )


async def generate_publishable_brief(
    desk: str,
    pool: asyncpg.Pool,
    evaluator: CitationEvaluator,
    *,
    min_claims: int | None = None,
    max_attempts: int | None = None,
) -> BriefAttempt:
    """Generate and evaluate a brief, regenerating on a failed gate OR a generation
    failure (D072).

    Returns the first attempt that clears ``min_claims``; if none do within
    ``max_attempts``, returns the best attempt (most provable claims) so the caller
    can still persist the strongest brief, marked failed. A generation/eval *exception*
    (e.g. the synthesis model returning a whitespace-only non-JSON body, or a transient
    provider error) is treated as a failed attempt and retried within the same budget,
    not propagated — so an unlucky draw can't crash an unattended desk run. If every
    attempt raises and none produced a brief, the last exception is re-raised as a
    RuntimeError so the caller's failure path still fires.
    """
    min_claims = settings.brief_min_claims if min_claims is None else min_claims
    max_attempts = settings.brief_max_attempts if max_attempts is None else max_attempts
    max_attempts = max(1, max_attempts)

    best: BriefAttempt | None = None
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            brief = await generate_brief(desk=desk, pool=pool)
            result = await evaluate_brief(brief, evaluator, min_claims)
        except Exception as exc:  # noqa: BLE001 — any generation/eval failure is a retryable bad draw
            last_exc = exc
            log.warning(
                "brief_attempt_failed",
                desk=desk,
                attempt=attempt,
                max_attempts=max_attempts,
                error=str(exc),
            )
            continue
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
        # A failed attempt now means zero honest items survived (or an exception);
        # keep the draw with the most surviving items, provable claims as tiebreak.
        if best is None or (
            len(result.surviving_items), result.provable_claims
        ) > (len(best.surviving_items), best.provable_claims):
            best = result

    if best is not None:
        return best
    # Every attempt raised — surface it on the caller's failure path (run_brief catches
    # RuntimeError), chaining the original cause for diagnosis.
    raise RuntimeError(
        f"Brief generation failed for desk '{desk}' after {max_attempts} attempt(s)"
    ) from last_exc
