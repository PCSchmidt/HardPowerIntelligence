"""Adapter registry — maps a ``source_registry.id`` to its adapter instance.

The ingestion runner looks up the adapter for a given ``source_id`` here rather
than importing concrete classes, so adding a source is: write the adapter, add
one line below, seed the ``source_registry`` row. Each adapter must expose the
ingestion contract: ``source_id``, ``base_url``, ``http_method``,
``build_request_payload(cursor, page)``, ``parse(response)``,
``next_cursor(response, current_page)``.
"""
from __future__ import annotations

from engine.adapters.arxiv import ArxivAdapter
from engine.adapters.edgar import EDGARFullTextAdapter
from engine.adapters.usaspending import USASpendingAdapter

# source_id → zero-arg adapter factory. New sources register one line here.
_ADAPTERS: dict[str, type] = {
    USASpendingAdapter.source_id: USASpendingAdapter,
    EDGARFullTextAdapter.source_id: EDGARFullTextAdapter,
    ArxivAdapter.source_id: ArxivAdapter,
}


def get_adapter(source_id: str):
    """Return a fresh adapter instance for ``source_id``.

    Raises KeyError with a clear message if the source has no registered adapter
    (e.g. a ``source_registry`` row exists but the adapter is unbuilt).
    """
    try:
        return _ADAPTERS[source_id]()
    except KeyError:
        known = ", ".join(sorted(_ADAPTERS)) or "(none)"
        raise KeyError(
            f"No adapter registered for source_id={source_id!r}. Known: {known}"
        ) from None


def registered_source_ids() -> list[str]:
    return sorted(_ADAPTERS)
