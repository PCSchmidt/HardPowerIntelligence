"""Generate ``docs/SOURCES.md`` — the authoritative, current-state list of wired data sources.

Source of truth is CODE, not a hand-maintained list (which drifts — see the stale
``SOURCE_LANDSCAPE.md`` candidate catalog). This reads the two registries directly:

- ``engine/adapters/registry._ADAPTERS`` — the structured/API adapters (one ``source_id`` each)
- ``engine/adapters/feeds._FEEDS``       — the RSS/Atom outlets under ``source_id="feeds"``

and their epistemic tier from ``engine/brief/epistemics``. Run after adding/removing any source:

    uv run python scripts/dump_sources.py     # writes docs/SOURCES.md

No timestamp is emitted, so a regen with no source change is a no-op diff. A drift guard
(``tests/unit/test_sources_doc.py``) fails if a wired source isn't present in the doc.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from engine.adapters.feeds import _FEEDS
from engine.adapters.registry import _ADAPTERS
from engine.brief.epistemics import PRIMARY, REPORTED, SIGNAL, evidence_class

_TIER = {
    PRIMARY: "Confirmed — primary public record (claims citation-supported)",
    REPORTED: "Reported — attributed named third-party",
    SIGNAL: "Speculative — raw / un-vetted signal",
}
_DESK_ORDER = ("defense", "ai", "energy")
_DESK_LABEL = {"defense": "Defense", "ai": "AI", "energy": "Energy"}
_OUT = Path(__file__).resolve().parents[1] / "docs" / "SOURCES.md"


def _adapter_description(adapter_cls: type) -> str:
    """First line of the adapter module's docstring — the code-owned one-liner."""
    module = inspect.getmodule(adapter_cls)
    doc = (getattr(module, "__doc__", "") or "").strip()
    return doc.splitlines()[0].strip() if doc else adapter_cls.__name__


def build() -> str:
    lines: list[str] = [
        "# Data Sources (wired)",
        "",
        "**Auto-generated — do not edit by hand.** Regenerate with "
        "`uv run python scripts/dump_sources.py` whenever a source is added or removed; the "
        "source of truth is `engine/adapters/registry.py` + `engine/adapters/feeds.py`. For the "
        "*candidate* universe and phased roadmap (not the live list), see `SOURCE_LANDSCAPE.md`. "
        "Live per-feed health is a runtime signal (the `feed_yielded_zero` ingest log), not tracked here.",
        "",
        "## Structured / API adapters",
        "",
        "Each is one `source_id` with its own adapter.",
        "",
        "| `source_id` | Tier | What it pulls |",
        "|---|---|---|",
    ]
    for source_id, adapter_cls in _ADAPTERS.items():
        tier = _TIER.get(evidence_class(source_id), evidence_class(source_id))
        lines.append(f"| `{source_id}` | {tier} | {_adapter_description(adapter_cls)} |")

    by_desk: dict[str, list] = {d: [] for d in _DESK_ORDER}
    for feed in _FEEDS:
        by_desk.setdefault(feed.desk, []).append(feed)

    feeds_tier = _TIER.get(evidence_class("feeds"), "Reported")
    lines += [
        "",
        f"## Feed outlets — `source_id=\"feeds\"` ({len(_FEEDS)} total)",
        "",
        f"One generic RSS/Atom adapter drives a registry of named outlets. Tier: {feeds_tier}. "
        "Each carries a single home desk (D097).",
        "",
    ]
    for desk in _DESK_ORDER:
        feeds = by_desk.get(desk, [])
        lines.append(f"### {_DESK_LABEL.get(desk, desk.capitalize())} ({len(feeds)})")
        lines.append("")
        for feed in feeds:
            lines.append(f"- **{feed.name}** — <{feed.url}>")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    _OUT.write_text(build(), encoding="utf-8")
    print(f"wrote {_OUT} — {len(_ADAPTERS)} adapters, {len(_FEEDS)} feeds")


if __name__ == "__main__":
    main()
