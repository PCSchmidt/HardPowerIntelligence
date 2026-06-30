"""Full Wire overflow capture (D112).

The wire is the material, on-thesis items that cleared scoring + home-desk routing but lost
the brief's space cut. persist_brief writes the pool minus whatever the published brief
features, best-effort (never darks a brief). Pure/fake-DB unit tests — no network.
"""
from datetime import datetime, timezone

from engine.brief.generator import GeneratedBrief, _wire_signal, persist_brief
from engine.brief.rag import PassageContext


class TestWireSignal:
    def test_prefers_structured_title(self):
        row = {
            "rr_id": "abc", "source_id": "edgar", "native_id": "0001",
            "record_type": "filing", "url": "https://x/y",
            "_sd": {"title": "Acme 8-K: material agreement"}, "text_chunk": "fallback",
        }
        s = _wire_signal(row, 0.6123456)
        assert s["record_id"] == "abc"
        assert s["source_id"] == "edgar"
        assert s["native_id"] == "0001"
        assert s["item_type"] == "filing"
        assert s["headline"] == "Acme 8-K: material agreement"
        assert s["url"] == "https://x/y"
        assert s["score"] == 0.6123          # rounded to 4 dp

    def test_falls_back_to_text_chunk(self):
        row = {"rr_id": "z", "source_id": "gdelt", "record_type": "news",
               "_sd": {}, "text_chunk": 'site.com reported: "Headline".'}
        s = _wire_signal(row, 0.4)
        assert s["headline"] == 'site.com reported: "Headline".'

    def test_truncates_long_title(self):
        row = {"rr_id": "z", "source_id": "gdelt", "record_type": "news",
               "_sd": {"title": "x" * 400}, "text_chunk": ""}
        assert len(_wire_signal(row, 0.4)["headline"]) == 300

    def test_tolerates_json_string_structured_data(self):
        row = {"rr_id": "z", "source_id": "edgar", "record_type": "filing",
               "_sd": '{"title": "From JSON"}', "text_chunk": "tc"}
        assert _wire_signal(row, 0.4)["headline"] == "From JSON"


# ── persist subtraction ──────────────────────────────────────────────────────────────

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

    async def fetch(self, sql, *args):
        return []          # entity-linking resolve runs on this; empty is fine

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


def _wire_rows():
    return [
        {"record_id": "rr-keep", "source_id": "usaspending", "native_id": "n1",
         "item_type": "award", "headline": "Kept signal", "url": "https://a", "score": 0.7},
        {"record_id": "rr-feat", "source_id": "edgar", "native_id": "n2",
         "item_type": "filing", "headline": "Featured signal", "url": "https://b", "score": 0.6},
    ]


async def test_persist_writes_wire_when_nothing_featured():
    conn = FakeConn()
    brief = GeneratedBrief(
        headline="H", bluf="B", items=[], passages=[],
        synthesis_model="m", model_waterfall_metadata={}, wire=_wire_rows(),
    )
    await persist_brief(
        brief=brief, desk="energy", brief_date="2026-06-30",
        faithfulness_score=1.0, eval_passed=True, excluded_item_ids=set(),
        pool=FakePool(conn),
    )
    inserts = [s for s in conn.executed if "INSERT INTO brief_wire" in s]
    assert len(inserts) == 2          # no featured items → both overflow rows persist


async def test_persist_excludes_records_featured_in_the_brief():
    # The brief features rr-feat (its item cites a passage backed by rr-feat) → that row must
    # NOT appear in the wire (it's already on the desk page); rr-keep still does.
    conn = FakeConn()
    passages = [PassageContext(
        index=1, raw_record_id="rr-feat", source_id="edgar", url="https://b",
        fetched_at=datetime.now(timezone.utc), native_id="n2", excerpt="e",
    )]
    item = {"_item_id": "item-0", "citation_indices": [1],
            "item_type": "filing", "headline": "h", "body": "b [CITE:1]"}
    brief = GeneratedBrief(
        headline="H", bluf="B", items=[item], passages=passages,
        synthesis_model="m", model_waterfall_metadata={}, wire=_wire_rows(),
    )
    await persist_brief(
        brief=brief, desk="energy", brief_date="2026-06-30",
        faithfulness_score=1.0, eval_passed=True, excluded_item_ids=set(),
        pool=FakePool(conn),
    )
    inserts = [s for s in conn.executed if "INSERT INTO brief_wire" in s]
    assert len(inserts) == 1          # rr-feat excluded as featured; only rr-keep remains
