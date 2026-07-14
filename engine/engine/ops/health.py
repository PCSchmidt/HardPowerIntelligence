"""Post-run health evaluation (Phase A / A1).

The daily cron's only alarm today is GitHub's native "workflow failed" email, which fires
ONLY on a hard crash (a brief job exiting non-zero). **Silent degradation** — a source failing
to ingest, a circuit breaker stuck open, the run going stale, or a total publish shutout that
still exits cleanly — never pages the operator, so they have to open the rendered desks each
morning to notice. This module turns the run's own telemetry (`briefs`, `ingestion_runs`,
`source_registry`) into a verdict so degradation alerts BEFORE the operator notices manually.

Key semantics (from `scripts/run_brief.py`): a published desk writes a brief row with
``status='published'``; a **clean thin-day skip** (below the provable-claim floor — normal, not
an error) persists ``status='failed'``; a **hard crash** returns before persist, leaving **no
row** for that (desk, date). So `status='failed'` is a *normal skip* and must not page — the real
signals are a total shutout, stuck/absent rows, and ingest-source degradation the workflow can't see.

Pure by design: `evaluate_health` takes plain dicts (queried by `scripts/run_health.py`) and
returns a `HealthReport`. The verdict maps to a process exit code so the existing GitHub email
channel fires on ``degraded``/``critical`` — no new alerting infra required (a webhook can be
added later).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

_EXPECTED_DESKS: tuple[str, ...] = ("defense", "ai", "energy")
_ATTRIBUTIONS = ("confirmed", "reported", "analysis", "speculative")
# Severity tiers. "critical"/"warn" flip the verdict (→ non-zero exit → GitHub failure email);
# "notice" surfaces in the report/digest but does NOT fail the run; "info" is normal-state context.
# "notice" (D132) exists so transient upstream flakiness — a source 500ing, a tripped breaker, a
# stale source — is visible without hard-failing every run and perpetually resetting the Phase-A
# "clean unattended days" gate. When such flakiness actually degrades output, the desk-level gates
# (brief_thin / confidence_collapsed / no_brief_published) still fire as warn/critical.
_LEVEL_ORDER = {"critical": 0, "warn": 1, "notice": 2, "info": 3}

# The D118 JSON-leak signature: an item body / analysis field that IS (or opens as) a JSON
# wrapper object rather than prose. A leading brace alone is too loose (prose can start "{...}"),
# so we also require a known wrapper key — conservative, to avoid false positives (A2 canary).
_LEAK_MARKERS = ('"rewritten"', '"analysis"', '"convergence_read"', '"text"', '"body"', '"read"', '"watch"')


def looks_like_content_leak(text: str) -> bool:
    """True if ``text`` looks like leaked synthesis JSON (a D118 regression) rather than prose."""
    t = (text or "").strip()
    return t.startswith("{") and any(m in t for m in _LEAK_MARKERS)


@dataclass(frozen=True)
class HealthThresholds:
    """Tunable bounds. Defaults are conservative — flag genuine anomalies, not sparse days."""
    min_items_per_brief: int = 4     # a PUBLISHED brief thinner than this is anomalously starved
    min_faithfulness: float = 0.98   # a published brief below the eval bar is a data smell
    source_stale_hours: int = 30     # an active source that once fetched but hasn't within this window
    run_token_budget: int = 0        # total completion tokens across desks above which cost warns (0=off)


@dataclass(frozen=True)
class Finding:
    level: str      # "critical" | "warn" | "notice" | "info"
    code: str       # stable machine code, e.g. "no_brief_published"
    message: str    # human-readable one-liner


@dataclass(frozen=True)
class HealthReport:
    verdict: str            # "ok" | "degraded" | "critical"
    findings: list[Finding]
    summary: str
    digest: list[str] = field(default_factory=list)   # always-shown run picture (A3)

    @property
    def exit_code(self) -> int:
        """0 only when healthy; non-zero (→ GitHub failure email) on degraded/critical."""
        return 0 if self.verdict == "ok" else 1


def _err(row: dict) -> str:
    msg = (row.get("error_message") or "").strip()
    return f" ({msg[:120]})" if msg else ""


def evaluate_health(
    *,
    briefs: list[dict],
    ingest_runs: list[dict],
    sources: list[dict],
    now: datetime,
    expected_desks: tuple[str, ...] = _EXPECTED_DESKS,
    thresholds: HealthThresholds | None = None,
) -> HealthReport:
    """Evaluate one day's run telemetry into a verdict. Pure — no I/O.

    ``briefs``: today's rows — ``desk``, ``status``, ``faithfulness_score``, ``item_count``.
    ``ingest_runs``: today's most-recent run per source — ``source_id``, ``status``, ``error_message``.
    ``sources``: ``source_registry`` — ``id``, ``is_active``, ``circuit_breaker_state``,
    ``last_successful_fetch_at``.
    """
    t = thresholds or HealthThresholds()
    findings: list[Finding] = []
    by_desk = {b.get("desk"): b for b in briefs}
    published = [d for d in expected_desks if by_desk.get(d, {}).get("status") == "published"]

    # ── Publish health ─────────────────────────────────────────────────────────────
    if not published:
        findings.append(Finding(
            "critical", "no_brief_published",
            "No desk published today — readers are seeing stale content.",
        ))
    for desk in expected_desks:
        b = by_desk.get(desk)
        if b is None:
            # No row = hard crash (returns before persist) or the desk never dispatched.
            findings.append(Finding(
                "warn", "brief_missing",
                f"{desk}: no brief row for today (crashed before persist, or didn't run).",
            ))
            continue
        status = b.get("status")
        if status == "published":
            items = b.get("item_count") or 0
            if items < t.min_items_per_brief:
                findings.append(Finding(
                    "warn", "brief_thin",
                    f"{desk}: published only {items} items (< {t.min_items_per_brief}) — starved upstream?",
                ))
            faith = b.get("faithfulness_score")
            if faith is not None and faith < t.min_faithfulness:
                findings.append(Finding(
                    "warn", "brief_low_faithfulness",
                    f"{desk}: published at faithfulness {faith:.3f} (< {t.min_faithfulness}).",
                ))
            # A2 — confidence-mix canary: a healthy brief is grounded (confirmed/reported). Zero
            # of both means it's entirely analysis/speculative — the sourcing collapsed.
            ac = b.get("attribution_counts") or {}
            if ac and (ac.get("confirmed", 0) + ac.get("reported", 0)) == 0:
                findings.append(Finding(
                    "warn", "confidence_collapsed",
                    f"{desk}: no confirmed/reported items — brief is entirely analysis/speculative.",
                ))
            # A2 — content-leak canary: catch a D118 JSON-leak regression in prod.
            texts = list(b.get("item_texts") or [])
            if b.get("convergence_read"):
                texts.append(b["convergence_read"])
            if any(looks_like_content_leak(x) for x in texts):
                findings.append(Finding(
                    "warn", "content_leak",
                    f"{desk}: an item body/analysis field looks like leaked JSON (D118 regression?).",
                ))
        elif status == "failed":
            # Distinguish two very different "failed" briefs. A synthesis that produced a
            # COMPLETE brief (headline present) yet persisted ZERO items didn't have a thin
            # news day — every item was stripped by the citation gate (the 2026-07-14 Defense
            # collapse: uncited item bodies deleted wholesale, D139). That is a silent desk-dark
            # and must page, unlike a genuine sparse day (some items, just below the claim floor).
            if (b.get("item_count") or 0) == 0 and (b.get("headline") or "").strip():
                findings.append(Finding(
                    "warn", "brief_items_collapsed",
                    f"{desk}: synthesis produced a full brief but 0 items survived the citation gate "
                    f"(citation-format drift, not a thin day) — desk is dark.",
                ))
            else:
                # A clean thin-day skip (below the claim floor). Normal — surface, don't alarm.
                findings.append(Finding(
                    "info", "brief_skipped",
                    f"{desk}: skipped (below the provable-claim floor — a thin news day).",
                ))
        elif status == "pending":
            findings.append(Finding(
                "warn", "brief_pending",
                f"{desk}: brief stuck 'pending' (generation didn't complete).",
            ))

    # ── Ingest-source health (the workflow never surfaces this) ──────────────────────
    # These are "notice" not "warn" (D132): a single source 500ing / timing out / going stale is
    # routine upstream flakiness that shouldn't fail an otherwise-healthy run. If it actually
    # starves a desk, the desk-level gates above escalate it to warn/critical.
    for run in ingest_runs:
        if run.get("status") == "failed":
            findings.append(Finding(
                "notice", "source_failed",
                f"ingest source '{run.get('source_id')}' failed{_err(run)}.",
            ))

    for s in sources:
        if not s.get("is_active", True):
            continue
        if s.get("circuit_breaker_state") == "open":
            findings.append(Finding(
                "notice", "circuit_open",
                f"source '{s.get('id')}' circuit breaker is OPEN (auto-tripped after repeated failures).",
            ))
        last = s.get("last_successful_fetch_at")
        if last is not None:
            age_h = (now - last).total_seconds() / 3600
            if age_h > t.source_stale_hours:
                findings.append(Finding(
                    "notice", "source_stale",
                    f"source '{s.get('id')}' last fetched {age_h:.0f}h ago (> {t.source_stale_hours}h).",
                ))

    # ── Cost (A4) — total completion tokens stamped on each brief by run_brief.py ─────
    tokens = [b.get("tokens") or {} for b in briefs]
    total_tokens = sum(int(tk.get("total_tokens", 0) or 0) for tk in tokens)
    total_calls = sum(int(tk.get("calls", 0) or 0) for tk in tokens)
    total_cost = sum(float(tk.get("est_cost_usd", 0.0) or 0.0) for tk in tokens)
    if t.run_token_budget and total_tokens > t.run_token_budget:
        findings.append(Finding(
            "warn", "cost_anomaly",
            f"run used {total_tokens:,} tokens (> budget {t.run_token_budget:,}) — a loop or regression?",
        ))

    # ── A3 digest — the always-shown daily picture (informational, separate from alerts) ─
    digest: list[str] = []
    for desk in expected_desks:
        b = by_desk.get(desk)
        if b and b.get("status") == "published":
            ac = b.get("attribution_counts") or {}
            mix = " / ".join(f"{ac.get(k, 0)} {k}" for k in _ATTRIBUTIONS)
            digest.append(f"{desk}: {b.get('item_count') or 0} items ({mix})")
        elif b and b.get("status") == "failed":
            if (b.get("item_count") or 0) == 0 and (b.get("headline") or "").strip():
                digest.append(f"{desk}: FAILED — full brief, 0 items survived (citation collapse)")
            else:
                digest.append(f"{desk}: skipped (thin day)")
        else:
            digest.append(f"{desk}: no brief")
    vol = sorted(
        ((r.get("source_id"), int(r.get("records_new", 0) or 0)) for r in ingest_runs),
        key=lambda x: -x[1],
    )
    vol_items = [f"{sid} +{n}" for sid, n in vol if n]
    digest.append("ingest: " + (", ".join(vol_items) if vol_items else "no new records"))
    if total_tokens:
        digest.append(f"LLM: {total_calls} calls, {total_tokens:,} tokens (~${total_cost:.2f} approx)")

    verdict = (
        "critical" if any(f.level == "critical" for f in findings)
        else "degraded" if any(f.level == "warn" for f in findings)
        else "ok"
    )
    crits = sum(1 for f in findings if f.level == "critical")
    warns = sum(1 for f in findings if f.level == "warn")
    notices = sum(1 for f in findings if f.level == "notice")
    summary = (
        f"{verdict.upper()} - {len(published)}/{len(expected_desks)} desks published; "
        f"{crits} critical, {warns} warnings, {notices} notices"
    )
    ordered = sorted(findings, key=lambda f: _LEVEL_ORDER.get(f.level, 9))
    return HealthReport(verdict=verdict, findings=ordered, summary=summary, digest=digest)
