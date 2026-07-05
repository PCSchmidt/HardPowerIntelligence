"""Post-run health check for the daily cron (Phase A / A1).

Queries today's run telemetry (briefs, ingestion_runs, source_registry), evaluates it
(`engine.ops.health.evaluate_health`), prints a report to stdout + the GitHub step summary,
and **exits non-zero on ``degraded``/``critical``** so the workflow goes red and GitHub's
failure email fires. This catches SILENT degradation — source failures, open circuit breakers,
stale sources, a total publish shutout — that the per-desk brief jobs never surface.

Runs as the final job after ingest + brief (see `.github/workflows/daily-brief.yml`).

Usage:
    python scripts/run_health.py [YYYY-MM-DD]   # defaults to today (UTC)
"""
import asyncio
import os
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, "engine")

from engine.db import create_pool
from engine.ops.health import HealthReport, evaluate_health

_ICON = {"critical": "[CRITICAL]", "warn": "[WARN]", "info": "[info]"}


async def _gather(pool, day: date) -> tuple[list[dict], list[dict], list[dict]]:
    day_start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    async with pool.acquire() as conn:
        briefs = await conn.fetch(
            """
            SELECT b.desk, b.status, b.faithfulness_score, b.error_message,
                   (SELECT count(*) FROM brief_items bi WHERE bi.brief_id = b.id) AS item_count
            FROM briefs b
            WHERE b.date = $1
            """,
            day,
        )
        # Most-recent ingestion run per source for the day.
        runs = await conn.fetch(
            """
            SELECT DISTINCT ON (source_id)
                   source_id, status, records_new, error_message, started_at
            FROM ingestion_runs
            WHERE started_at >= $1
            ORDER BY source_id, started_at DESC
            """,
            day_start,
        )
        sources = await conn.fetch(
            "SELECT id, is_active, circuit_breaker_state, last_successful_fetch_at FROM source_registry"
        )
    return [dict(r) for r in briefs], [dict(r) for r in runs], [dict(r) for r in sources]


def _emit(report: HealthReport, day: date) -> None:
    lines = [f"## Run health — {day} — {report.summary}", ""]
    if report.findings:
        lines += [f"- {_ICON.get(f.level, '-')} **{f.code}** — {f.message}" for f in report.findings]
    else:
        lines.append("- [ok] all clear")
    text = "\n".join(lines)
    print(text)
    gh_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if gh_summary:
        with open(gh_summary, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


async def main(day: date) -> int:
    pool = await create_pool()
    try:
        briefs, runs, sources = await _gather(pool, day)
    finally:
        await pool.close()
    report = evaluate_health(
        briefs=briefs, ingest_runs=runs, sources=sources, now=datetime.now(timezone.utc)
    )
    _emit(report, day)
    return report.exit_code


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    target = date.fromisoformat(arg) if arg else datetime.now(timezone.utc).date()
    sys.exit(asyncio.run(main(target)))
