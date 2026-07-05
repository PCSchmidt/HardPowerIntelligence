"""Run-health evaluator (Phase A / A1).

Verdict semantics under test:
- a clean thin-day skip persists status='failed' → INFO, must NOT page (normal sparse day);
- a total publish shutout → CRITICAL (readers see stale content);
- ingest-source failures / open breakers / stale sources → WARN (the workflow never surfaces these);
- verdict maps to exit code (0 only when ok).
"""
from datetime import datetime, timedelta, timezone

from engine.ops.health import HealthThresholds, evaluate_health

NOW = datetime(2026, 7, 6, 7, 0, tzinfo=timezone.utc)


def _brief(desk, status="published", item_count=20, faithfulness=1.0):
    return {"desk": desk, "status": status, "item_count": item_count,
            "faithfulness_score": faithfulness, "error_message": None}


def _fresh_source(sid="usaspending"):
    return {"id": sid, "is_active": True, "circuit_breaker_state": "closed",
            "last_successful_fetch_at": NOW - timedelta(hours=2)}


def _all_published():
    return [_brief("defense"), _brief("ai"), _brief("energy")]


def _codes(report):
    return {f.code for f in report.findings}


class TestHealthyDay:
    def test_all_published_is_ok(self):
        report = evaluate_health(
            briefs=_all_published(), ingest_runs=[], sources=[_fresh_source()], now=NOW
        )
        assert report.verdict == "ok"
        assert report.exit_code == 0
        assert not any(f.level in ("warn", "critical") for f in report.findings)

    def test_one_thin_day_skip_still_ok_and_does_not_page(self):
        # A skipped desk persists status='failed' — normal sparse day, must be INFO not WARN.
        briefs = [_brief("defense"), _brief("ai"), _brief("energy", status="failed")]
        report = evaluate_health(briefs=briefs, ingest_runs=[], sources=[_fresh_source()], now=NOW)
        assert report.verdict == "ok"
        assert "brief_skipped" in _codes(report)
        assert report.exit_code == 0


class TestPublishShutout:
    def test_no_desk_published_is_critical(self):
        # All three skipped (thin) — no publish at all → readers see stale content.
        briefs = [_brief(d, status="failed") for d in ("defense", "ai", "energy")]
        report = evaluate_health(briefs=briefs, ingest_runs=[], sources=[], now=NOW)
        assert report.verdict == "critical"
        assert "no_brief_published" in _codes(report)
        assert report.exit_code == 1

    def test_empty_run_is_critical(self):
        report = evaluate_health(briefs=[], ingest_runs=[], sources=[], now=NOW)
        assert report.verdict == "critical"
        assert "no_brief_published" in _codes(report)


class TestBriefDegradation:
    def test_missing_desk_row_warns(self):
        # Hard crash returns before persist → no row for that desk.
        briefs = [_brief("defense"), _brief("ai")]
        report = evaluate_health(briefs=briefs, ingest_runs=[], sources=[], now=NOW)
        assert report.verdict == "degraded"
        assert "brief_missing" in _codes(report)

    def test_thin_published_brief_warns(self):
        briefs = [_brief("defense", item_count=2), _brief("ai"), _brief("energy")]
        report = evaluate_health(briefs=briefs, ingest_runs=[], sources=[], now=NOW)
        assert "brief_thin" in _codes(report)
        assert report.verdict == "degraded"

    def test_thin_threshold_is_tunable(self):
        briefs = [_brief("defense", item_count=6), _brief("ai"), _brief("energy")]
        report = evaluate_health(
            briefs=briefs, ingest_runs=[], sources=[], now=NOW,
            thresholds=HealthThresholds(min_items_per_brief=10),
        )
        assert "brief_thin" in _codes(report)

    def test_low_faithfulness_warns(self):
        briefs = [_brief("defense", faithfulness=0.5), _brief("ai"), _brief("energy")]
        report = evaluate_health(briefs=briefs, ingest_runs=[], sources=[], now=NOW)
        assert "brief_low_faithfulness" in _codes(report)

    def test_pending_brief_warns(self):
        briefs = [_brief("defense", status="pending"), _brief("ai"), _brief("energy")]
        report = evaluate_health(briefs=briefs, ingest_runs=[], sources=[], now=NOW)
        assert "brief_pending" in _codes(report)
        assert report.verdict == "degraded"


class TestIngestAndSourceHealth:
    def test_failed_ingest_source_warns(self):
        runs = [{"source_id": "edgar", "status": "failed", "error_message": "EFTS 500"}]
        report = evaluate_health(
            briefs=_all_published(), ingest_runs=runs, sources=[], now=NOW
        )
        assert "source_failed" in _codes(report)
        assert report.verdict == "degraded"

    def test_open_circuit_breaker_warns(self):
        sources = [{"id": "gdelt", "is_active": True, "circuit_breaker_state": "open",
                    "last_successful_fetch_at": NOW - timedelta(hours=1)}]
        report = evaluate_health(
            briefs=_all_published(), ingest_runs=[], sources=sources, now=NOW
        )
        assert "circuit_open" in _codes(report)

    def test_stale_source_warns(self):
        sources = [{"id": "usaspending", "is_active": True, "circuit_breaker_state": "closed",
                    "last_successful_fetch_at": NOW - timedelta(hours=48)}]
        report = evaluate_health(
            briefs=_all_published(), ingest_runs=[], sources=sources, now=NOW
        )
        assert "source_stale" in _codes(report)

    def test_never_run_source_does_not_warn_stale(self):
        # Seeded-but-unwired source (last_successful_fetch_at NULL) must not false-alarm.
        sources = [{"id": "fred", "is_active": True, "circuit_breaker_state": "closed",
                    "last_successful_fetch_at": None}]
        report = evaluate_health(
            briefs=_all_published(), ingest_runs=[], sources=sources, now=NOW
        )
        assert "source_stale" not in _codes(report)
        assert report.verdict == "ok"

    def test_inactive_source_is_ignored(self):
        sources = [{"id": "dod_contracts", "is_active": False, "circuit_breaker_state": "open",
                    "last_successful_fetch_at": NOW - timedelta(days=10)}]
        report = evaluate_health(
            briefs=_all_published(), ingest_runs=[], sources=sources, now=NOW
        )
        assert report.verdict == "ok"


class TestReportShape:
    def test_findings_sorted_critical_first(self):
        briefs = [_brief("defense", status="failed"), _brief("ai", status="failed"),
                  _brief("energy", status="failed")]
        sources = [{"id": "gdelt", "is_active": True, "circuit_breaker_state": "open",
                    "last_successful_fetch_at": NOW}]
        report = evaluate_health(briefs=briefs, ingest_runs=[], sources=sources, now=NOW)
        assert report.findings[0].level == "critical"
        assert report.verdict == "critical"

    def test_summary_reports_publish_count(self):
        report = evaluate_health(
            briefs=_all_published(), ingest_runs=[], sources=[], now=NOW
        )
        assert "3/3 desks published" in report.summary
