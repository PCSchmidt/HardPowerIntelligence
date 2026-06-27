"""persist_brief idempotency (D058).

Spec: persisting a brief for (desk, date) first DELETEs any existing brief for
that day (cascades to items + citations), then inserts — so re-runs replace
instead of raising UniqueViolation, and a passing brief can supersede a failed one.
"""
from engine.brief.generator import GeneratedBrief, _is_home_desk, persist_brief


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
