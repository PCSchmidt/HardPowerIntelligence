"""GDELT media-attention signal (D082).

A *complementary* signal layer, deliberately separate from the citable-record pipeline.
GDELT's own aggregate data (volume/tone time series) is openly licensed; what we never
do is republish the third-party article text it indexes. So this produces a **labeled,
attributed, aggregate momentum signal** — "attention on theme X is up N% vs its trailing
baseline" — that is attached to a brief as disclaimed color, NOT a verified fact and NOT a
candidate record competing for `brief_max_items` slots (the D055 guardrail, kept by design).

Backend v1 is the keyless GDELT DOC 2.0 API `timelinevol` mode (one call per theme, no GCP
setup). The momentum math here is backend-agnostic, so a richer BigQuery GKG backend
(co-occurrence, GCAM, cross-entity → entity_edges) can replace the fetch layer later without
touching the brief-side Signal contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field

GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


def timeline_params(query: str, timespan: str = "6w") -> dict:
    """DOC 2.0 query params for a per-theme volume time series (share of all coverage)."""
    return {"query": query, "mode": "timelinevol", "format": "json", "timespan": timespan}


def parse_timeline(payload: dict) -> list[float]:
    """Extract the daily volume series (oldest→newest) from a timelinevol response."""
    timeline = (payload or {}).get("timeline") or []
    if not timeline:
        return []
    data = timeline[0].get("data") or []
    out: list[float] = []
    for point in data:
        try:
            out.append(float(point.get("value", 0.0)))
        except (TypeError, ValueError):
            continue
    return out


@dataclass
class Momentum:
    recent: float            # mean volume over the recent window
    baseline: float          # mean volume over the trailing baseline window
    delta_pct: float | None  # % change recent vs baseline; None if baseline ~0
    points: int              # number of series points seen

    @property
    def is_rising(self) -> bool:
        return self.delta_pct is not None and self.delta_pct >= 25.0

    @property
    def is_falling(self) -> bool:
        return self.delta_pct is not None and self.delta_pct <= -25.0


def compute_momentum(
    series: list[float], recent_days: int = 7, baseline_days: int = 21
) -> Momentum:
    """Recent-window mean vs. the immediately-preceding baseline-window mean.

    Designed to degrade gracefully on short series (GDELT can return sparse data): if
    there isn't enough history for a separate baseline, ``delta_pct`` is ``None`` (we
    report the level but make no momentum claim) rather than a misleading number."""
    n = len(series)
    if n == 0:
        return Momentum(recent=0.0, baseline=0.0, delta_pct=None, points=0)
    recent_vals = series[-recent_days:]
    baseline_vals = series[-(recent_days + baseline_days):-recent_days]
    recent = sum(recent_vals) / len(recent_vals) if recent_vals else 0.0
    baseline = sum(baseline_vals) / len(baseline_vals) if baseline_vals else 0.0
    delta = ((recent - baseline) / baseline * 100.0) if baseline > 0 else None
    return Momentum(recent=recent, baseline=baseline, delta_pct=delta, points=n)


@dataclass
class ThemeSignal:
    theme: str
    momentum: Momentum
    series: list[float] = field(default_factory=list)

    def phrase(self) -> str | None:
        """A short human phrase for this theme's momentum, or None if not noteworthy."""
        m = self.momentum
        if m.delta_pct is None:
            return None
        if m.is_rising:
            return f"{self.theme} +{m.delta_pct:.0f}%"
        if m.is_falling:
            return f"{self.theme} {m.delta_pct:.0f}%"
        return None


def build_signal_line(signals: list[ThemeSignal]) -> str:
    """A single labeled, disclaimed signal line for a brief, or "" if nothing moved.

    Only themes with a noteworthy move are named, so the line is honest about how much
    GDELT actually saw — an empty result means "no attention shift worth flagging,"
    not a fabricated trend."""
    phrases = [p for s in signals if (p := s.phrase())]
    if not phrases:
        return ""
    return (
        "Signal · GDELT media attention (aggregate momentum, not a verified fact): "
        + "; ".join(phrases[:5])
        + "."
    )


@dataclass
class BriefSignal:
    """A brief's GDELT signal (D082/D089): the labeled prose ``line`` plus the lead theme's
    volume series for a sparkline. The series fields are the numeric layer — empty/None when
    nothing moved or GDELT was unreachable, so the reader shows the line with no sparkline."""
    line: str
    lead_theme: str | None = None
    series: list[float] = field(default_factory=list)
    delta_pct: float | None = None
    direction: str | None = None   # "up" | "down" | None

    def series_json(self) -> dict | None:
        """JSONB payload for ``briefs.signal_series``, or None when there's no sparkline."""
        if not self.series or self.lead_theme is None:
            return None
        return {
            "theme": self.lead_theme,
            "series": self.series,
            "delta_pct": self.delta_pct,
            "direction": self.direction,
        }


async def compute_brief_signal(
    themes: list[str], fetcher, *, max_themes: int = 6
) -> BriefSignal:
    """Fetch momentum for up to ``max_themes`` themes; return the labeled line plus the lead
    theme's series for a sparkline.

    Capped to bound GDELT calls per brief. The lead is the noteworthy theme with the largest
    absolute move; if nothing moved (or GDELT is unreachable) ``line`` is "" and there is no
    sparkline — the brief simply renders no Signal block."""
    signals = [await fetch_theme_signal(t, fetcher) for t in themes[:max_themes]]
    line = build_signal_line(signals)
    if not line:
        return BriefSignal(line="")
    noteworthy = [s for s in signals if s.phrase() is not None]
    lead = max(noteworthy, key=lambda s: abs(s.momentum.delta_pct or 0.0))
    direction = (
        "up" if lead.momentum.is_rising else "down" if lead.momentum.is_falling else None
    )
    return BriefSignal(
        line=line,
        lead_theme=lead.theme,
        series=lead.series,
        delta_pct=lead.momentum.delta_pct,
        direction=direction,
    )


async def fetch_theme_signal(theme: str, fetcher, *, timespan: str = "6w") -> ThemeSignal:
    """Fetch one theme's volume series and compute its momentum (best-effort).

    Any fetch/parse failure yields an empty momentum (delta None) rather than raising —
    the Signal layer is decorative; it must never fail a brief."""
    try:
        payload = await fetcher.fetch_json(
            "GET", GDELT_DOC_URL, params=timeline_params(theme, timespan),
            response_format="json",
        )
        series = parse_timeline(payload if isinstance(payload, dict) else {})
    except Exception:  # noqa: BLE001 — decorative signal must not fail the brief
        series = []
    return ThemeSignal(theme=theme, momentum=compute_momentum(series), series=series)
