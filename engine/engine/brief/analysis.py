"""Analysis grounding gate (D073): regenerate-then-omit.

The layered brief (D071) carries an analysis layer — per-item ``read``/``watch`` and a
brief-level ``convergence_read`` — that is interpretation, not cited claim. It is held
to grounding by ``CitationEvaluator.eval_analysis`` (analyst voice: flag only fabricated
specifics about the cited subjects), but the synthesis model still occasionally invents
a checkable detail (e.g. a "CARLA-VR integration" not in the paper).

This module is the gate that runs before persistence: for each analysis field, if the
evaluator flags it, rewrite it once (``analysis_max_regen``) to strip the fabrication
while keeping the analyst voice, re-check, and if it still doesn't ground, **omit** the
field (store ``""``). So a persisted/rendered analysis is always grounded — an empty
field means analysis was withheld, never that a fabrication leaked through (the trust
model, mirroring D069 for facts).
"""
from dataclasses import dataclass

import structlog

from engine.brief.generator import GeneratedBrief, _unwrap_analysis_field
from engine.eval.citation_eval import CitationEvaluator
from engine.llm.client import llm_client
from engine.settings import settings

log = structlog.get_logger()


@dataclass
class FieldGrounding:
    """Outcome of grounding one analysis field."""
    label: str
    status: str          # "empty" | "grounded" | "regenerated" | "omitted"
    text: str            # the grounded text to persist ("" if empty/omitted)
    fabrications: list[str]   # the flagged specifics that forced regen/omit


async def _regenerate(
    label: str, prior: str, fabrications: list[str], facts: str, model: str
) -> str:
    """Rewrite an analysis field to remove fabricated specifics, keeping analyst voice."""
    flagged = "\n".join(f"- {f}" for f in fabrications) or "- (unspecified)"
    messages = [
        {
            "role": "system",
            "content": (
                "You revise one ANALYSIS paragraph from an investment-research brief. The "
                "prior version invented a SPECIFIC, checkable detail about the cited subjects "
                "that the verified facts do not support. Rewrite it to remove ONLY the "
                "fabricated specific(s), preserving the analyst's interpretation, real-world "
                "domain context, and hedged forward-looking inference. Introduce no new "
                "specific (number, name, date, quantity, or definite event) absent from the "
                "facts, add no citations, and give no buy/sell advice. If nothing grounded "
                "remains to say, return an empty string. Return only the rewritten prose, no "
                "preamble."
            ),
        },
        {
            "role": "user",
            "content": (
                f"VERIFIED FACTS:\n{facts}\n\n"
                f"FABRICATED SPECIFICS TO REMOVE:\n{flagged}\n\n"
                f"ANALYSIS TO FIX:\n{prior}"
            ),
        },
    ]
    content = await llm_client.complete(
        model=model, messages=messages, temperature=settings.llm_temperature,
    )
    # Unwrap a stray JSON wrapper the rewrite model sometimes returns ({"rewritten": "..."}) —
    # otherwise it renders verbatim on the desk page (the D118 leak, regen branch).
    return _unwrap_analysis_field((content or "").strip())


async def _reground(
    label: str,
    text: str,
    fabrications: list[str],
    facts: str,
    evaluator: CitationEvaluator,
    *,
    model: str,
    max_regen: int,
) -> FieldGrounding:
    """Regenerate-then-omit an ALREADY-flagged field: rewrite up to ``max_regen`` times to strip
    the fabricated specifics, re-check each rewrite, and omit (``""``) if it still won't ground."""
    original = list(fabrications)
    for _ in range(max(0, max_regen)):
        rewritten = await _regenerate(label, text, fabrications, facts, model)
        if not rewritten:
            break
        verdict = await evaluator.eval_analysis(rewritten, facts)
        if verdict.grounded:
            return FieldGrounding(label, "regenerated", rewritten, original)
        text, fabrications = rewritten, verdict.new_facts
    log.info("analysis_omitted", label=label, fabrications=original)
    return FieldGrounding(label, "omitted", "", original)


async def ground_field(
    label: str,
    text: str,
    facts: str,
    evaluator: CitationEvaluator,
    *,
    model: str,
    max_regen: int,
) -> FieldGrounding:
    """Ground a single analysis field: pass through if grounded, else regenerate-then-omit.

    Standalone path (one eval + regen loop). The brief pipeline uses the batched
    :func:`ground_brief_analysis` instead — this remains for single-field grounding/tests."""
    text = (text or "").strip()
    if not text:
        return FieldGrounding(label, "empty", "", [])

    verdict = await evaluator.eval_analysis(text, facts)
    if verdict.grounded:
        return FieldGrounding(label, "grounded", text, [])
    return await _reground(
        label, text, verdict.new_facts, facts, evaluator, model=model, max_regen=max_regen,
    )


async def ground_brief_analysis(
    brief: GeneratedBrief,
    items: list[dict],
    facts: str,
    evaluator: CitationEvaluator,
    *,
    max_regen: int | None = None,
    model: str | None = None,
) -> list[FieldGrounding]:
    """Ground every analysis field of a brief in place before persistence (D073).

    Mutates ``brief.convergence_read`` and each item's ``read``/``watch`` to the grounded
    text (or ``""`` if omitted). ``items`` should be the surviving items only, so omitted
    facts don't cost regeneration. Returns the per-field grounding report.

    Batched (D119): the grounding eval runs ONCE for every field — the (large) facts block is
    sent a single time, not re-sent per field. The old per-field loop made ~2·N eval calls each
    re-transmitting the facts (~56/desk on a full brief), which was the token sink and the 12-min
    timeout tail (D118). Only the rare FLAGGED field then takes the per-field regenerate-then-omit
    path. Field order is fixed so the returned report is deterministic.
    """
    max_regen = settings.analysis_max_regen if max_regen is None else max_regen
    model = model or settings.llm_model_synthesis

    # Fixed-order field list: (label, stripped_text). Labels index back to the write target.
    fields: list[tuple[str, str]] = [("convergence_read", (brief.convergence_read or "").strip())]
    for i, item in enumerate(items):
        for key in ("read", "watch"):
            fields.append((f"item{i}.{key}", (item.get(key) or "").strip()))

    nonempty = [(label, text) for label, text in fields if text]
    verdicts = await evaluator.eval_analyses_batch(nonempty, facts) if nonempty else {}

    grounded_text: dict[str, str] = {}
    report: list[FieldGrounding] = []
    for label, text in fields:
        if not text:
            grounded_text[label] = ""
            report.append(FieldGrounding(label, "empty", "", []))
            continue
        verdict = verdicts.get(label)
        if verdict is None or verdict.grounded:
            grounded_text[label] = text
            report.append(FieldGrounding(label, "grounded", text, []))
            continue
        res = await _reground(
            label, text, verdict.new_facts, facts, evaluator, model=model, max_regen=max_regen,
        )
        grounded_text[label] = res.text
        report.append(res)

    brief.convergence_read = grounded_text["convergence_read"]
    for i, item in enumerate(items):
        item["read"] = grounded_text[f"item{i}.read"]
        item["watch"] = grounded_text[f"item{i}.watch"]

    return report
