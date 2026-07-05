"""Post-run health check for the daily cron (Phase A / A1-A4).

Queries today's run telemetry (briefs + their items, ingestion_runs, source_registry),
evaluates it (`engine.ops.health.evaluate_health`), prints a **digest** (the daily picture) plus
any **findings** (anomalies), and **exits non-zero on ``degraded``/``critical``** so the workflow
goes red and GitHub's failure email fires. Catches silent degradation — source failures, open
breakers, stale sources, a total shutout (A1) — plus a collapsed confidence-mix / leaked-JSON
regression (A2) and a token-cost anomaly (A4). Runs as the final job after ingest + brief.

Usage:
    python scripts/run_health.py [YYYY-MM-DD]   # defaults to today (UTC)
"""
import asyncio
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone

sys.path.insert(0, "engine")

from engine.db import create_pool
from engine.ops.health import HealthReport, HealthThresholds, evaluate_health
from engine.settings import settings

_ICON = {"critical": "[CRITICAL]", "warn": "[WARN]", "info": "[info]"}


def _as_dict(meta) -> dict:
    if isinstance(meta, str):
        try:
            return json.loads(meta)
        except (ValueError, TypeError):
            return {}
    return meta or {}


async def _gather(pool, day: date) -> tuple[list[dict], list[dict], list[dict]]:
    day_start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    async with pool.acquire() as conn:
        brief_rows = await conn.fetch(
            """
            SELECT b.id, b.desk, b.status, b.faithfulness_score, b.error_message,
                   b.convergence_read, b.model_waterfall_metadata,
                   (SELECT count(*) FROM brief_items bi WHERE bi.brief_id = b.id) AS item_count
            FROM briefs b
            WHERE b.date = $1
            """,
            day,
        )
        item_rows = await conn.fetch(
            """
            SELECT bi.brief_id, bi.attribution, bi.body, bi.read, bi.watch
            FROM brief_items bi
            JOIN briefs b ON b.id = bi.brief_id
            WHERE b.date = $1
            """,
            day,
        )
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

    attr: dict = defaultdict(Counter)
    texts: dict = defaultdict(list)
    for r in item_rows:
        bid = r["brief_id"]
        attr[bid][r["attribution"]] += 1
        texts[bid].extend(v for v in (r["body"], r["read"], r["watch"]) if v)

    briefs: list[dict] = []
    for row in brief_rows:
        d = dict(row)
        bid = d.pop("id")
        d["attribution_counts"] = dict(attr.get(bid, {}))
        d["item_texts"] = texts.get(bid, [])
        d["tokens"] = _as_dict(d.get("model_waterfall_metadata")).get("tokens") or {}
        briefs.append(d)
    return briefs, [dict(r) for r in runs], [dict(r) for r in sources]


def _emit(report: HealthReport, day: date) -> None:
    lines = [f"## Run health — {day} — {report.summary}", ""]
    for d in report.digest:
        lines.append(f"- {d}")
    lines.append("")
    if report.findings:
        lines += [f"- {_ICON.get(f.level, '-')} **{f.code}** — {f.message}" for f in report.findings]
    else:
        lines.append("- [ok] no anomalies")
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
        briefs=briefs, ingest_runs=runs, sources=sources, now=datetime.now(timezone.utc),
        thresholds=HealthThresholds(run_token_budget=settings.llm_run_token_budget),
    )
    _emit(report, day)
    return report.exit_code


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    target = date.fromisoformat(arg) if arg else datetime.now(timezone.utc).date()
    sys.exit(asyncio.run(main(target)))
