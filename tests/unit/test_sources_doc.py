"""Drift guard for docs/SOURCES.md — the auto-generated wired-sources inventory.

If a source is added/removed in the registries but the doc wasn't regenerated
(`uv run python scripts/dump_sources.py`), this fails — so the inventory stays honest rather
than rotting like the SOURCE_LANDSCAPE candidate catalog did. Checks presence, not formatting.
"""
from pathlib import Path

from engine.adapters.feeds import _FEEDS
from engine.adapters.registry import _ADAPTERS

_DOC = Path(__file__).resolve().parents[2] / "docs" / "SOURCES.md"


def _text() -> str:
    return _DOC.read_text(encoding="utf-8")


def test_doc_exists():
    assert _DOC.exists(), "docs/SOURCES.md missing — run scripts/dump_sources.py"


def test_every_adapter_source_id_documented():
    missing = [sid for sid in _ADAPTERS if f"`{sid}`" not in _text()]
    assert not missing, f"SOURCES.md stale — regenerate; missing adapters: {missing}"


def test_every_feed_outlet_documented():
    text = _text()
    missing = [f.name for f in _FEEDS if f.name not in text]
    assert not missing, f"SOURCES.md stale — regenerate; missing feeds: {missing}"


def test_feed_count_matches_registry():
    assert f"({len(_FEEDS)} total)" in _text(), "SOURCES.md feed count stale — regenerate"
