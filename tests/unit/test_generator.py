"""persist_brief idempotency (D058).

Spec: persisting a brief for (desk, date) first DELETEs any existing brief for
that day (cascades to items + citations), then inserts — so re-runs replace
instead of raising UniqueViolation, and a passing brief can supersede a failed one.
"""
from engine.brief.generator import (
    GeneratedBrief,
    _is_home_desk,
    _license_class_for,
    _overflow_wire,
    persist_brief,
)


def _cand(rid: str, score: float = 0.5):
    row = {
        "rr_id": rid, "source_id": "gdelt", "record_type": "news",
        "url": f"https://x/{rid}", "native_id": rid, "text_chunk": f"item {rid}",
        "_sd": {},
    }
    return (row, score)


class TestOverflowWire:
    """Full Wire supply = material candidates minus significance froth (D112). Froth is
    computed by DIFFERENCE (selected − kept), because the significance gate's `dropped`
    list carries descriptions, not records — indexing it as a record was the D115 crash
    ("string indices must be integers") that darkened all three desks."""

    def test_froth_computed_by_difference_and_beyond_selection_kept(self):
        A, B, C, D = _cand("A", 0.9), _cand("B", 0.8), _cand("C", 0.7), _cand("D", 0.6)
        candidates = [A, B, C, D]
        selected = [A, B, C]          # top-N chosen as synthesis input
        facts = [A, C]                # significance dropped B as froth
        wire = _overflow_wire(candidates, selected, facts)
        ids = {w["record_id"] for w in wire}
        assert ids == {"A", "C", "D"}  # B (froth) excluded; D (below the fact cut) still surfaced
        assert "B" not in ids

    def test_no_froth_keeps_every_candidate(self):
        A, B = _cand("A"), _cand("B")
        wire = _overflow_wire([A, B], [A, B], [A, B])
        assert {w["record_id"] for w in wire} == {"A", "B"}


class TestLicenseClassForSource:
    """Citation license_class derives from the source (D101), not a hardcoded value:
    GDELT is third-party news → scrape_gray (title + link only); gov/regulatory primary
    data → public_domain. Drives full-quote vs link-only rendering in the reader."""

    def test_gdelt_is_scrape_gray(self):
        assert _license_class_for("gdelt") == "scrape_gray"

    def test_primary_sources_are_public_domain(self):
        for src in ("usaspending", "edgar", "nrc", "arxiv", ""):
            assert _license_class_for(src) == "public_domain"


class _Txn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeConn:
    def __init__(self):
        self.executed: list[str] = []

    async def execute(self, sql, *args):
        self.executed.append(sql)

    def transaction(self):
        return _Txn()


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *a):
        return False


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Acquire(self.conn)


def _brief() -> GeneratedBrief:
    return GeneratedBrief(
        headline="H", bluf="B", items=[], passages=[],
        synthesis_model="m", model_waterfall_metadata={},
    )


async def test_persist_deletes_existing_before_insert():
    conn = FakeConn()
    await persist_brief(
        brief=_brief(), desk="defense", brief_date="2026-06-14",
        faithfulness_score=1.0, eval_passed=True, excluded_item_ids=set(),
        pool=FakePool(conn),
    )
    deletes = [i for i, s in enumerate(conn.executed) if "DELETE FROM briefs" in s]
    inserts = [i for i, s in enumerate(conn.executed) if "INSERT INTO briefs" in s]
    assert deletes and inserts, "expected both a delete and an insert"
    assert deletes[0] < inserts[0], "delete must precede insert (idempotent replace)"


async def test_persist_failed_brief_also_replaces():
    # A failed brief must still clear a prior row so a later passing run can publish.
    conn = FakeConn()
    await persist_brief(
        brief=_brief(), desk="defense", brief_date="2026-06-14",
        faithfulness_score=0.0, eval_passed=False, excluded_item_ids=set(),
        pool=FakePool(conn),
    )
    assert any("DELETE FROM briefs" in s for s in conn.executed)


class TestPrimaryDeskRouting:
    """Primary-desk routing (desk-bleed fix): a cross-desk record surfaces only on
    its home desk — the first element of its ordered ``desk`` array — so it stops
    duplicating onto every tagged desk. Cross-desk relevance survives as the
    convergence marker (desk_count boost / entity chip), not a duplicate item."""

    def test_home_desk_is_first_array_element(self):
        # "hyperscale data center" → (ai, energy): AI is home, Energy is convergence.
        row = {"desk": ["ai", "energy"]}
        assert _is_home_desk(row, "ai") is True

    def test_secondary_desk_is_not_home(self):
        # Same record must NOT surface on Energy — that was the bleed.
        row = {"desk": ["ai", "energy"]}
        assert _is_home_desk(row, "energy") is False

    def test_single_desk_record_routes_to_its_only_desk(self):
        row = {"desk": ["defense"]}
        assert _is_home_desk(row, "defense") is True

    def test_empty_or_missing_desk_routes_nowhere(self):
        assert _is_home_desk({"desk": []}, "ai") is False
        assert _is_home_desk({}, "ai") is False
        assert _is_home_desk({"desk": None}, "ai") is False


async def test_persist_writes_layered_fields():
    # D073: the analysis layer (convergence_read / read / watch) is persisted.
    conn = FakeConn()
    brief = GeneratedBrief(
        headline="H", bluf="B",
        items=[{"item_type": "filing", "headline": "i0", "body": "b0",
                "read": "R0", "watch": "W0", "citation_indices": []}],
        passages=[], synthesis_model="m", model_waterfall_metadata={},
        convergence_read="Cross-desk thesis.",
    )
    await persist_brief(
        brief=brief, desk="defense", brief_date="2026-06-14",
        faithfulness_score=1.0, eval_passed=True, excluded_item_ids=set(),
        pool=FakePool(conn),
    )
    briefs_insert = next(s for s in conn.executed if "INSERT INTO briefs" in s)
    items_insert = next(s for s in conn.executed if "INSERT INTO brief_items" in s)
    assert "convergence_read" in briefs_insert
    assert "read" in items_insert and "watch" in items_insert
