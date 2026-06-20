"""Brief endpoint helpers (pure). The quiet-day "latest available" indicator (vs the D013
pending/failed staleness) decides whether a reader on a quiet day sees yesterday's date with
context or with none."""
from datetime import date

from app.routers.briefs import _latest_available_indicator


def test_no_indicator_when_brief_is_todays():
    today = date(2026, 6, 20)
    assert _latest_available_indicator({"date": today, "published_at": None}, today) is None


def test_no_indicator_when_brief_is_future_dated():
    today = date(2026, 6, 20)
    assert _latest_available_indicator({"date": date(2026, 6, 21), "published_at": None}, today) is None


def test_indicator_when_brief_is_older_than_today():
    today = date(2026, 6, 20)
    ind = _latest_available_indicator({"date": date(2026, 6, 18), "published_at": "ts"}, today)
    assert ind is not None
    assert ind["current_status"] == "latest_available"      # not pending/failed (D013)
    assert "most recent brief" in ind["message"]
    assert ind["last_updated"] == "ts"
