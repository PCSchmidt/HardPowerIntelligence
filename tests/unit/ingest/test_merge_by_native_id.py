"""Cross-probe filing dedup (D107) — engine/ingest/runner._merge_by_native_id.

A full-text adapter (EDGAR) parses one filing once per matching (query, desk) probe,
so the same native_id arrives several times with conflicting desk primacy. The merge
keeps ONE record per (source_id, native_id):
  * desk[] = UNION of every matching probe's desks (the convergence signal survives);
  * home (desk[0]) = the MOST-SPECIFIC probe's primary (fewest desks wins);
  * exact specificity ties broken by _DESK_TIEBREAK;
  * order-independent.
This is what stops the same filing printing on multiple desks under D097 routing.
"""
from engine.adapters.base import NormalizedRecord
from engine.ingest.runner import _merge_by_native_id


def _rec(native_id: str, desks: list[str], theme: str) -> NormalizedRecord:
    # theme varies the content_hash exactly as the live adapter does — the reason the
    # raw_records UNIQUE(source_id, native_id, content_hash) dedup does NOT collapse these.
    return NormalizedRecord(
        source_id="edgar",
        record_type="filing",
        desk=list(desks),
        entity_mentions=[],
        structured_data={"accession": native_id, "theme": theme},
        text_chunk=f"{native_id} {theme}",
        content_hash=f"hash-{native_id}-{theme}",
        native_id=native_id,
    )


def test_same_filing_collapses_to_one_record():
    records = [
        _rec("0001", ["defense", "ai", "energy"], "rare earth"),
        _rec("0001", ["energy", "defense"], "uranium enrichment"),
    ]
    merged = _merge_by_native_id(records)
    assert len(merged) == 1


def test_home_desk_is_most_specific_probe():
    # rare earth = 3 desks (home defense); uranium enrichment = 2 desks (home energy).
    # The narrower probe wins the home, so the filing lands on Energy, not Defense.
    records = [
        _rec("0001", ["defense", "ai", "energy"], "rare earth"),
        _rec("0001", ["energy", "defense"], "uranium enrichment"),
    ]
    [m] = _merge_by_native_id(records)
    assert m.desk[0] == "energy"


def test_desks_are_unioned_for_convergence():
    records = [
        _rec("0001", ["defense", "ai", "energy"], "rare earth"),
        _rec("0001", ["energy", "defense"], "uranium enrichment"),
    ]
    [m] = _merge_by_native_id(records)
    assert set(m.desk) == {"defense", "ai", "energy"}
    assert m.desk[0] == "energy"  # home stays first


def test_order_independent():
    a = _rec("0001", ["defense", "ai", "energy"], "rare earth")
    b = _rec("0001", ["energy", "defense"], "uranium enrichment")
    forward = _merge_by_native_id([a, b])[0]
    # fresh copies so in-place desk mutation from the first call can't leak
    reverse = _merge_by_native_id([
        _rec("0001", ["energy", "defense"], "uranium enrichment"),
        _rec("0001", ["defense", "ai", "energy"], "rare earth"),
    ])[0]
    assert forward.desk[0] == reverse.desk[0] == "energy"
    assert set(forward.desk) == set(reverse.desk)


def test_distinct_filings_are_preserved():
    records = [
        _rec("0001", ["energy"], "geothermal"),
        _rec("0002", ["defense"], "hypersonic"),
        _rec("0003", ["ai"], "high bandwidth memory"),
    ]
    merged = _merge_by_native_id(records)
    assert {m.native_id for m in merged} == {"0001", "0002", "0003"}


def test_equal_specificity_tie_broken_by_priority():
    # Two 2-desk probes disagree on home; _DESK_TIEBREAK = (defense, energy, ai) → defense.
    records = [
        _rec("0001", ["energy", "ai"], "immersion cooling"),
        _rec("0001", ["defense", "ai"], "counter-unmanned aircraft"),
    ]
    [m] = _merge_by_native_id(records)
    assert m.desk[0] == "defense"
    assert set(m.desk) == {"defense", "energy", "ai"}


def test_single_desk_probe_beats_multi_desk():
    # A 1-desk match is the strongest possible home signal.
    records = [
        _rec("0001", ["defense", "ai", "energy"], "rare earth"),
        _rec("0001", ["energy"], "geothermal"),
    ]
    [m] = _merge_by_native_id(records)
    assert m.desk[0] == "energy"


def test_empty_desk_records_skipped():
    records = [_rec("0001", [], "weird")]
    assert _merge_by_native_id(records) == []
