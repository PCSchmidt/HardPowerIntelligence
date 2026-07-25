"""Credit-runway evaluation in evaluate_health (D156).

The balance is read TOGETHER with the publish outcome: dry + nothing published = both lanes failed
(billing_exhausted, critical — the 2026-07-24 dark); dry + published = the cross-provider backstop
served (running_on_backstop, warn — refill the primary); low-but-not-dry warns early.
"""
from datetime import datetime, timedelta, timezone

from engine.ops.health import evaluate_health

NOW = datetime(2026, 7, 25, 7, 0, tzinfo=timezone.utc)


def _pub(desk):
    return {"desk": desk, "status": "published", "item_count": 20, "faithfulness_score": 1.0}


def _all_pub():
    return [_pub("defense"), _pub("ai"), _pub("energy")]


def _all_failed():
    return [{"desk": d, "status": "failed", "item_count": 20} for d in ("defense", "ai", "energy")]


def _src():
    return {"id": "usaspending", "is_active": True, "circuit_breaker_state": "closed",
            "last_successful_fetch_at": NOW - timedelta(hours=2)}


def _bal(remaining, reachable=True, provider="openrouter", detail=""):
    return [{"provider": provider, "reachable": reachable, "remaining_usd": remaining, "detail": detail}]


def _codes(r):
    return {f.code for f in r.findings}


def _level(r, code):
    return next((f.level for f in r.findings if f.code == code), None)


def _eval(briefs, balances):
    return evaluate_health(briefs=briefs, ingest_runs=[], sources=[_src()], now=NOW,
                           provider_balances=balances)


class TestCreditRunway:
    def test_healthy_balance_no_finding_but_shown_in_digest(self):
        r = _eval(_all_pub(), _bal(42.0))
        assert r.verdict == "ok"
        assert not ({"billing_exhausted", "running_on_backstop", "credit_runway_low"} & _codes(r))
        assert any("openrouter credits: $42.00" in d for d in r.digest)

    def test_low_balance_warns_early(self):
        r = _eval(_all_pub(), _bal(3.0))
        assert _level(r, "credit_runway_low") == "warn"
        assert r.verdict == "degraded"

    def test_exhausted_but_published_is_running_on_backstop_warn(self):
        r = _eval(_all_pub(), _bal(0.10))
        assert _level(r, "running_on_backstop") == "warn"
        assert "billing_exhausted" not in _codes(r)

    def test_exhausted_and_no_brief_is_billing_exhausted_critical(self):
        r = _eval(_all_failed(), _bal(0.0))
        assert _level(r, "billing_exhausted") == "critical"
        assert r.verdict == "critical"

    def test_probe_failure_warns_runway_unknown(self):
        r = _eval(_all_pub(), _bal(None, reachable=False, detail="HTTP 500"))
        assert _level(r, "balance_check_failed") == "warn"
        assert any("openrouter credits: check failed" in d for d in r.digest)

    def test_no_balances_is_backward_compatible(self):
        r = evaluate_health(briefs=_all_pub(), ingest_runs=[], sources=[_src()], now=NOW)
        assert r.verdict == "ok" and not _codes(r)
