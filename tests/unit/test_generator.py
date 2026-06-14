"""persist_brief idempotency (D058).

Spec: persisting a brief for (desk, date) first DELETEs any existing brief for
that day (cascades to items + citations), then inserts — so re-runs replace
instead of raising UniqueViolation, and a passing brief can supersede a failed one.
"""
from engine.brief.generator import GeneratedBrief, persist_brief


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
