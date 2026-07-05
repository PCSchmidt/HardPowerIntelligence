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

from dataclasses import dataclass
from datetime import datetime

_EXPECTED_DESKS: tuple[str, ...] = ("defense", "ai", "energy")
_LEVEL_ORDER = {"critical": 0, "warn": 1, "info": 2}


@dataclass(frozen=True)
class HealthThresholds:
    """Tunable bounds. Defaults are conservative — flag genuine anomalies, not sparse days."""
    min_items_per_brief: int = 4     # a PUBLISHED brief thinner than this is anomalously starved
    min_faithfulness: float = 0.98   # a published brief below the eval bar is a data smell
    source_stale_hours: int = 30     # an active source that once fetched but hasn't within this window


@dataclass(frozen=True)
class Finding:
    level: str      # "critical" | "warn" | "info"
    code: str       # stable machine code, e.g. "no_brief_published"
    message: str    # human-readable one-liner


@dataclass(frozen=True)
class HealthReport:
    verdict: str            # "ok" | "degraded" | "critical"
    findings: list[Finding]
    summary: str

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
        elif status == "failed":
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
    for run in ingest_runs:
        if run.get("status") == "failed":
            findings.append(Finding(
                "warn", "source_failed",
                f"ingest source '{run.get('source_id')}' failed{_err(run)}.",
            ))

    for s in sources:
        if not s.get("is_active", True):
            continue
        if s.get("circuit_breaker_state") == "open":
            findings.append(Finding(
                "warn", "circuit_open",
                f"source '{s.get('id')}' circuit breaker is OPEN (auto-tripped after repeated failures).",
            ))
        last = s.get("last_successful_fetch_at")
        if last is not None:
            age_h = (now - last).total_seconds() / 3600
            if age_h > t.source_stale_hours:
                findings.append(Finding(
                    "warn", "source_stale",
                    f"source '{s.get('id')}' last fetched {age_h:.0f}h ago (> {t.source_stale_hours}h).",
                ))

    verdict = (
        "critical" if any(f.level == "critical" for f in findings)
        else "degraded" if any(f.level == "warn" for f in findings)
        else "ok"
    )
    crits = sum(1 for f in findings if f.level == "critical")
    warns = sum(1 for f in findings if f.level == "warn")
    summary = (
        f"{verdict.upper()} - {len(published)}/{len(expected_desks)} desks published; "
        f"{crits} critical, {warns} warnings"
    )
    ordered = sorted(findings, key=lambda f: _LEVEL_ORDER.get(f.level, 9))
    return HealthReport(verdict=verdict, findings=ordered, summary=summary)
