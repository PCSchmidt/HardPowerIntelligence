"""Strategic-significance gate (D085).

Materiality (D035) ranks candidates by source authority, novelty, dollar magnitude, and
entity importance — but a record can score well and still be *strategically trivial*: a
routine cellular-service contract, a filing that discloses no material event, a years-old
award resurfacing. The publish gate (D070) guarantees every claim is true and cited, but
true ≠ significant. This gate adds the missing "so what?" judgment: after materiality
selection, an LLM triage scores each candidate's significance for the desk thesis and
drops the clearly-insignificant before synthesis.

Safety: **fail-open** (a candidate the model didn't score is kept, so an LLM hiccup never
silently drops good material) and it **never empties the pool** (if everything scores low,
the single best survives, and the publish gate decides whether the thin result publishes or
the desk cleanly skips). Both keep this from turning a quiet news day into a hard failure.
"""
from __future__ import annotations

import structlog

from engine.llm.client import llm_client, parse_json
from engine.settings import settings

log = structlog.get_logger()

Fact = tuple[dict, float]  # (candidate record, materiality score)

_SYSTEM = (
    "You curate a {desk} intelligence brief for sophisticated defense/energy/AI investors "
    "and analysts. Rate each candidate item's STRATEGIC SIGNIFICANCE for the {desk} desk "
    "from 0.0 to 1.0. Favor OPERATING SUBSTANCE over financial-vehicle mechanics: a "
    "sophisticated investor treats a blank-check SPAC racing to close or a shell company "
    "rebranding as froth, not signal. "
    "Score LOW (<0.4): routine commodity procurement (cellular/telecom service, office IT, "
    "facilities, leases, food/janitorial); content-free or administrative filings (bylaw "
    "amendments, auditor ratifications, routine Section 16) disclosing no specific material "
    "event; stale or years-old actions resurfacing; AND speculative financial vehicles — "
    "SPAC / de-SPAC / blank-check business combinations (especially pre- or no-revenue "
    "targets), cash shells recapitalizing, pivoting, or rebranding via acquisition or name "
    "change, and non-binding term sheets / LOIs / MOUs whose substance is the deal vehicle "
    "itself (a blank-check finding a target, a shell acquiring a business). "
    "Score HIGH (>0.6): binding or closed M&A, financings, and project finance by OPERATING "
    "companies; material capital deployment into real assets or capacity; new or strategically "
    "relevant programs / contracts / awards; genuine technology milestones from operating "
    "companies; supply-chain or critical-mineral developments; consequential policy. A "
    "non-binding agreement still scores HIGH when the underlying development is materially "
    "strategic and the parties are operating companies (e.g., a domestic HALEU or "
    "critical-mineral supply or offtake LOI). Judge significance, not whether it is cited. "
    "Return only JSON: "
    '{{"scores": [{{"id": 0, "score": 0.0, "reason": "<=8 words"}}]}}'
)


def _describe(candidate: dict) -> str:
    return (candidate.get("text_chunk") or "").strip().replace("\n", " ")[:300]


def apply_significance(
    facts: list[Fact],
    scores: dict[int, tuple[float, str]],
    threshold: float,
) -> tuple[list[Fact], list[tuple[str, float, str]]]:
    """Pure: keep facts scoring >= threshold (fail-open for unscored), never return empty.

    Returns (kept_facts, dropped) where dropped is (description, score, reason)."""
    enumerated = []
    for i, (cand, mat) in enumerate(facts):
        score, reason = scores.get(i, (1.0, "unscored"))  # fail-open: unscored is kept
        enumerated.append((i, cand, mat, score, reason))

    kept = [(c, m) for (_i, c, m, s, _r) in enumerated if s >= threshold]
    dropped = [
        (_describe(c), s, r) for (_i, c, _m, s, r) in enumerated if s < threshold
    ]
    if not kept and enumerated:
        # Never empty the pool — keep the single best so the publish gate, not this gate,
        # decides whether a thin day publishes or skips.
        best = max(enumerated, key=lambda e: e[3])
        kept = [(best[1], best[2])]
        dropped = [d for d in dropped if d[0] != _describe(best[1])]
    return kept, dropped


async def _score_facts(facts: list[Fact], desk: str) -> dict[int, tuple[float, str]]:
    model = settings.significance_model or settings.llm_model_eval
    block = "\n".join(f"id={i}: {_describe(c)}" for i, (c, _m) in enumerate(facts))
    messages = [
        {"role": "system", "content": _SYSTEM.format(desk=desk)},
        {"role": "user", "content": f"CANDIDATE ITEMS:\n{block}"},
    ]
    content = await llm_client.complete(
        model=model, messages=messages, json_mode=True,
        temperature=settings.llm_temperature,
    )
    parsed = parse_json(content) or {}
    out: dict[int, tuple[float, str]] = {}
    for s in parsed.get("scores", []):
        try:
            out[int(s["id"])] = (float(s.get("score", 0.0)), str(s.get("reason", "")))
        except (KeyError, TypeError, ValueError):
            continue
    return out


async def filter_significant(facts: list[Fact], desk: str) -> tuple[list[Fact], list]:
    """Drop strategically-trivial candidates before synthesis (D085).

    Best-effort: if the triage call fails, keep everything (fail-open) — a junk filter
    must never be the reason a brief fails to generate."""
    if not settings.significance_enabled or not facts:
        return facts, []
    try:
        scores = await _score_facts(facts, desk)
    except Exception as exc:  # noqa: BLE001 — triage is advisory; never fail the brief on it
        log.warning("significance_triage_failed", desk=desk, error=str(exc)[:200])
        return facts, []
    return apply_significance(facts, scores, settings.significance_threshold)
