"""GDELT media-attention signal (D082) — pure compute, no network."""
import pytest
from engine.signal.gdelt import (
    BriefSignal,
    ThemeSignal,
    build_signal_line,
    compute_brief_signal,
    compute_momentum,
    fetch_theme_signal,
    parse_timeline,
    timeline_params,
)

_RISING = {"timeline": [{"series": "v", "data": [
    {"date": f"d{i}", "value": v} for i, v in enumerate([1.0] * 21 + [2.0] * 7)
]}]}


class TestTimelineParse:
    def test_params_shape(self):
        p = timeline_params("small modular reactor")
        assert p["mode"] == "timelinevol" and p["format"] == "json"
        assert p["query"] == "small modular reactor"

    def test_parse_extracts_values_oldest_to_newest(self):
        payload = {"timeline": [{"series": "Volume Intensity", "data": [
            {"date": "20260501T000000Z", "value": 0.1},
            {"date": "20260502T000000Z", "value": 0.2},
        ]}]}
        assert parse_timeline(payload) == [0.1, 0.2]

    def test_parse_empty(self):
        assert parse_timeline({}) == []
        assert parse_timeline({"timeline": []}) == []


class TestMomentum:
    def test_rising_series_positive_delta(self):
        # 21 days of baseline ~1.0, then 7 days of ~2.0 → +100%
        series = [1.0] * 21 + [2.0] * 7
        m = compute_momentum(series)
        assert m.delta_pct == pytest.approx(100.0)
        assert m.is_rising and not m.is_falling

    def test_falling_series_negative_delta(self):
        series = [2.0] * 21 + [1.0] * 7
        m = compute_momentum(series)
        assert m.delta_pct == pytest.approx(-50.0)
        assert m.is_falling

    def test_flat_series_not_noteworthy(self):
        m = compute_momentum([1.0] * 28)
        assert m.delta_pct == pytest.approx(0.0)
        assert not m.is_rising and not m.is_falling

    def test_zero_baseline_yields_none_delta(self):
        # no attention in baseline window → no honest % claim possible
        m = compute_momentum([0.0] * 21 + [0.5] * 7)
        assert m.delta_pct is None

    def test_empty_series(self):
        m = compute_momentum([])
        assert m.delta_pct is None and m.points == 0


class TestSignalLine:
    def test_only_noteworthy_themes_named(self):
        rising = ThemeSignal("SMRs", compute_momentum([1.0] * 21 + [2.0] * 7))
        flat = ThemeSignal("rare earth", compute_momentum([1.0] * 28))
        line = build_signal_line([rising, flat])
        assert "SMRs +100%" in line
        assert "rare earth" not in line          # flat themes omitted, not faked
        assert "not a verified fact" in line      # disclaimer present

    def test_empty_when_nothing_moves(self):
        flat = ThemeSignal("x", compute_momentum([1.0] * 28))
        assert build_signal_line([flat]) == ""


class _FakeFetcher:
    def __init__(self, payload=None, fail=False):
        self.payload = payload or {}
        self.fail = fail
        self.calls = 0

    async def fetch_json(self, method, url, *, params=None, response_format="json", **kw):
        self.calls += 1
        if self.fail:
            raise RuntimeError("gdelt down")
        return self.payload


class TestFetchThemeSignal:
    @pytest.mark.asyncio
    async def test_fetch_and_compute(self):
        payload = {"timeline": [{"series": "v", "data": [
            {"date": f"2026050{i}T000000Z", "value": v}
            for i, v in enumerate([1.0] * 21 + [2.0] * 7)
        ]}]}
        sig = await fetch_theme_signal("SMRs", _FakeFetcher(payload))
        assert sig.theme == "SMRs"
        assert sig.momentum.is_rising

    @pytest.mark.asyncio
    async def test_fetch_failure_is_silent(self):
        sig = await fetch_theme_signal("SMRs", _FakeFetcher(fail=True))
        assert sig.momentum.delta_pct is None    # decorative: never raises
        assert sig.series == []                  # no series to sparkline

    @pytest.mark.asyncio
    async def test_fetch_carries_series(self):
        payload = {"timeline": [{"series": "v", "data": [
            {"date": f"2026050{i}T000000Z", "value": v} for i, v in enumerate([1.0, 2.0, 3.0])
        ]}]}
        sig = await fetch_theme_signal("SMRs", _FakeFetcher(payload))
        assert sig.series == [1.0, 2.0, 3.0]     # raw series flows through for the sparkline


class TestComputeBriefSignal:
    @pytest.mark.asyncio
    async def test_caps_theme_count_and_builds_labeled_line(self):
        fetcher = _FakeFetcher(_RISING)
        sig = await compute_brief_signal(list("abcdefgh"), fetcher, max_themes=3)
        assert fetcher.calls == 3                 # capped, not all 8 themes
        assert "not a verified fact" in sig.line and "+100%" in sig.line

    @pytest.mark.asyncio
    async def test_lead_theme_carries_series_for_sparkline(self):
        sig = await compute_brief_signal(list("abc"), _FakeFetcher(_RISING), max_themes=3)
        assert sig.lead_theme in {"a", "b", "c"}
        assert len(sig.series) == 28               # the lead theme's 28-pt volume series
        assert sig.direction == "up"
        payload = sig.series_json()
        assert payload is not None
        assert payload["series"] == sig.series and payload["direction"] == "up"

    @pytest.mark.asyncio
    async def test_gdelt_unreachable_yields_empty_line(self):
        sig = await compute_brief_signal(["a", "b"], _FakeFetcher(fail=True))
        assert sig.line == ""                       # no signal block rendered
        assert sig.series_json() is None            # and no sparkline

    def test_series_json_none_without_series(self):
        assert BriefSignal(line="x").series_json() is None
