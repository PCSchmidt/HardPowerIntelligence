"""Post-run health check for the daily cron (Phase A / A1-A4).

Queries today's run telemetry (briefs + their items, ingestion_runs, source_registry),
evaluates it (`engine.ops.health.evaluate_health`), prints a **digest** (the daily picture) plus
any **findings** (anomalies), and **exits non-zero on ``degraded``/``critical``** so the workflow
goes red and GitHub's failure email fires. Fails on genuine degradation — a total shutout (A1),
a thin/low-faithfulness brief, a collapsed confidence-mix / leaked-JSON regression (A2), a
token-cost anomaly (A4). Transient upstream source flakiness (failures, open breakers, stale
sources) is surfaced as a non-failing **notice** (D132) so it doesn't reset the Phase-A gate;
it still escalates to a failure via the desk gates if it actually starves a desk. Runs as the
final job after ingest + brief.

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
from engine.ops.notify import alert_payload, send_resend_alert
from engine.ops.provider_balance import fetch_openrouter_balance
from engine.settings import settings

_ICON = {"critical": "[CRITICAL]", "warn": "[WARN]", "notice": "[notice]", "info": "[info]"}


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
                   b.headline, b.convergence_read, b.model_waterfall_metadata,
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
    # Credit-runway probe (D156) — best-effort; a probe failure surfaces as a finding, never a crash.
    balance = await fetch_openrouter_balance(settings.openrouter_api_key)
    report = evaluate_health(
        briefs=briefs, ingest_runs=runs, sources=sources, now=datetime.now(timezone.utc),
        thresholds=HealthThresholds(
            run_token_budget=settings.llm_run_token_budget,
            credit_low_usd=settings.credit_low_usd,
            credit_exhausted_usd=settings.credit_exhausted_usd,
        ),
        provider_balances=[balance.as_dict()],
    )
    _emit(report, day)
    # Push an out-of-band alert for act-now conditions (billing / critical) so degradation is caught
    # in minutes, not via stale reader briefs days later (D156). Best-effort — never blocks the exit.
    payload = alert_payload(report, day)
    if payload:
        _sent, detail = await send_resend_alert(
            *payload, api_key=settings.resend_api_key,
            to=settings.alert_email_to, sender=settings.alert_email_from,
        )
        print(f"[alert] push (resend): {detail}")
    return report.exit_code


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    target = date.fromisoformat(arg) if arg else datetime.now(timezone.utc).date()
    sys.exit(asyncio.run(main(target)))
