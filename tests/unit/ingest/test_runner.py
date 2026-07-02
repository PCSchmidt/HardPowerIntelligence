"""Ingestion runner control-flow + dedup logic.

Uses a fake asyncpg pool/connection (records SQL, scripts INSERT...RETURNING
results) and a fake fetcher (canned API pages), driving the *real* USASpending
adapter so parsing and dedup counting are genuinely exercised — not mocked away.

Spec (engine/ingest/runner.py):
- new vs duplicate is decided by raw_records INSERT...RETURNING (id → new, None → dup);
- only NEW raw_records get a normalized_record (no double-normalize on dup);
- pagination follows next_cursor {"page": n} until a non-page cursor;
- inactive source / open breaker → status 'skipped', no fetch;
- a fetch exception → status 'failed', run + breaker recorded, no raise.
"""
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from engine.ingest.runner import _breaker_blocks, run_source


def _http_status_error(code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://api.sam.gov/opportunities/v2/search")
    resp = httpx.Response(code, request=req)
    return httpx.HTTPStatusError(f"HTTP {code}", request=req, response=resp)


def _sam_page(notice_id: str = "n1") -> dict:
    return {"opportunitiesData": [{
        "noticeId": notice_id, "title": "Hypersonic Test Range Services",
        "fullParentPathName": "DEPT OF DEFENSE", "type": "Solicitation",
        "postedDate": "2026-06-25", "uiLink": f"https://sam.gov/opp/{notice_id}/view",
    }]}

NOW = datetime.now(timezone.utc)


# ── fakes ────────────────────────────────────────────────────────────────────

class _Txn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeConn:
    def __init__(self, source_row, raw_returns):
        self.source_row = source_row
        self._raw_returns = list(raw_returns)
        self.executed: list[str] = []
        self.normalized_inserts = 0

    async def fetchrow(self, sql, *args):
        if "FROM source_registry" in sql:
            return self.source_row
        return None

    async def fetchval(self, sql, *args):
        if "INSERT INTO raw_records" in sql:
            return self._raw_returns.pop(0) if self._raw_returns else None
        return 0

    async def execute(self, sql, *args):
        self.executed.append(sql)
        if "INSERT INTO normalized_records" in sql:
            self.normalized_inserts += 1

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


class FakeFetcher:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def fetch_json(self, method, url, **kwargs):
        resp = self.responses[self.calls]
        self.calls += 1
        if isinstance(resp, Exception):
            raise resp
        return resp


# ── helpers ──────────────────────────────────────────────────────────────────

def make_source(**over):
    base = dict(
        id="usaspending", is_active=True, circuit_breaker_state="closed",
        circuit_breaker_opened_at=None, last_cursor=None,
    )
    base.update(over)
    return base


def make_award(award_id, recipient="ACME CORP", amount=1_000_000.0):
    return {
        "Award ID": award_id, "Recipient Name": recipient, "Award Amount": amount,
        "Awarding Agency": "Department of Defense", "Award Description": "Widget program",
    }


def make_response(awards, has_next=False):
    return {
        "results": awards,
        "page_metadata": {"has_next_page": has_next},
        "total_count": len(awards),
    }


# ── breaker (pure) ───────────────────────────────────────────────────────────

def test_breaker_closed_does_not_block():
    assert _breaker_blocks(make_source(circuit_breaker_state="closed"), NOW) is False


def test_breaker_open_within_cooldown_blocks():
    src = make_source(circuit_breaker_state="open", circuit_breaker_opened_at=NOW)
    assert _breaker_blocks(src, NOW) is True


def test_breaker_open_after_cooldown_allows_trial():
    src = make_source(
        circuit_breaker_state="open",
        circuit_breaker_opened_at=NOW - timedelta(hours=1),
    )
    assert _breaker_blocks(src, NOW) is False


# ── run_source ───────────────────────────────────────────────────────────────

async def test_counts_new_and_duplicate():
    # 3 awards; DB says first two are new (return id), third conflicts (None).
    # max_pages=1 keeps this a single-page test independent of the adapter's probe count.
    conn = FakeConn(make_source(), raw_returns=["id1", "id2", None])
    pool = FakePool(conn)
    fetcher = FakeFetcher([make_response([make_award("A"), make_award("B"), make_award("C")])])

    result = await run_source("usaspending", pool, fetcher=fetcher, embed=False, max_pages=1)

    assert result.status == "success"
    assert result.records_fetched == 3
    assert result.records_new == 2
    assert result.records_duplicate == 1


async def test_only_new_records_are_normalized():
    conn = FakeConn(make_source(), raw_returns=["id1", None])
    pool = FakePool(conn)
    fetcher = FakeFetcher([make_response([make_award("A"), make_award("B")])])

    await run_source("usaspending", pool, fetcher=fetcher, embed=False, max_pages=1)

    assert conn.normalized_inserts == 1  # only the new raw_record, not the dup


async def test_rate_limited_source_is_throttled(monkeypatch):
    # GDELT declares min_request_interval; the runner spaces requests (sleeping before every
    # request except the first) so the probe walk can't trip HTTP 429 and zero the source (D109).
    sleeps: list[float] = []

    async def fake_sleep(secs):
        sleeps.append(secs)

    monkeypatch.setattr("engine.ingest.runner.asyncio.sleep", fake_sleep)

    conn = FakeConn(make_source(id="gdelt"), raw_returns=[])
    pool = FakePool(conn)
    empty = {"articles": []}
    fetcher = FakeFetcher([empty, empty, empty])

    result = await run_source("gdelt", pool, fetcher=fetcher, embed=False, max_pages=3)

    assert result.status == "success"
    assert fetcher.calls == 3              # three requests made
    assert len(sleeps) == 2                # spaced before the 2nd and 3rd, never the 1st
    assert all(s >= 5.0 for s in sleeps)   # at least GDELT's min interval


async def test_pagination_advances_through_pages():
    # The runner advances page-by-page via next_cursor until max_pages or a terminal cursor.
    conn = FakeConn(make_source(), raw_returns=["id1", "id2"])
    pool = FakePool(conn)
    fetcher = FakeFetcher([
        make_response([make_award("A")]),
        make_response([make_award("B")]),
    ])

    result = await run_source("usaspending", pool, fetcher=fetcher, embed=False, max_pages=2)

    assert fetcher.calls == 2
    assert result.pages_fetched == 2
    assert result.records_fetched == 2


async def test_max_pages_caps_pagination():
    conn = FakeConn(make_source(), raw_returns=["x"] * 10)
    pool = FakePool(conn)
    # Every page claims another page exists — runner must stop at max_pages.
    fetcher = FakeFetcher([make_response([make_award(str(i))], has_next=True) for i in range(10)])

    result = await run_source("usaspending", pool, fetcher=fetcher, embed=False, max_pages=3)

    assert result.pages_fetched == 3
    assert fetcher.calls == 3


async def test_inactive_source_is_skipped_without_fetch():
    conn = FakeConn(make_source(is_active=False), raw_returns=[])
    pool = FakePool(conn)
    fetcher = FakeFetcher([])

    result = await run_source("usaspending", pool, fetcher=fetcher, embed=False)

    assert result.status == "skipped"
    assert fetcher.calls == 0


async def test_open_breaker_is_skipped_without_fetch():
    src = make_source(circuit_breaker_state="open", circuit_breaker_opened_at=NOW)
    conn = FakeConn(src, raw_returns=[])
    pool = FakePool(conn)
    fetcher = FakeFetcher([])

    result = await run_source("usaspending", pool, fetcher=fetcher, embed=False)

    assert result.status == "skipped"
    assert fetcher.calls == 0


async def test_fetch_failure_records_failed_run_without_raising():
    conn = FakeConn(make_source(), raw_returns=[])
    pool = FakePool(conn)
    fetcher = FakeFetcher([RuntimeError("network down")])

    result = await run_source("usaspending", pool, fetcher=fetcher, embed=False)

    assert result.status == "failed"
    assert "network down" in result.error
    # The failure path updates ingestion_runs + source_registry (breaker).
    assert any("UPDATE ingestion_runs" in s for s in conn.executed)
    assert any("circuit_breaker_failures" in s for s in conn.executed)


async def test_unknown_source_raises():
    # Programmer error (no adapter) must fail loud, unlike ingestion failures.
    conn = FakeConn(make_source(id="nope"), raw_returns=[])
    pool = FakePool(conn)
    with pytest.raises(KeyError):
        await run_source("nope", pool, fetcher=FakeFetcher([]), embed=False)


async def test_empty_response_status_is_tolerated_and_walk_continues():
    # SAM returns 404 for a probe with no title match (D114). The adapter declares 404 as
    # empty, so the FIRST probe's 404 must NOT fail the source — the walk continues and a
    # later probe's real results are persisted.
    conn = FakeConn(make_source(id="sam_gov"), raw_returns=["id1"])
    pool = FakePool(conn)
    fetcher = FakeFetcher([_http_status_error(404), _sam_page("n1")])

    result = await run_source("sam_gov", pool, fetcher=fetcher, embed=False, max_pages=2)

    assert result.status == "success"
    assert result.records_new == 1        # page 1 (404) empty, page 2 opportunity persisted
    assert fetcher.calls == 2             # did not stop after the 404


async def test_non_empty_4xx_still_fails_the_source():
    # A status NOT in empty_response_statuses (e.g. 403 auth) is a real failure, not "no match".
    conn = FakeConn(make_source(id="sam_gov"), raw_returns=[])
    pool = FakePool(conn)
    fetcher = FakeFetcher([_http_status_error(403)])

    result = await run_source("sam_gov", pool, fetcher=fetcher, embed=False, max_pages=2)

    assert result.status == "failed"


class _RecordingFetcher:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    async def fetch_json(self, method, url, **kwargs):
        self.kwargs = kwargs
        return self.response


async def test_gdelt_patient_backoff_hints_reach_the_fetcher():
    # D117: GDELT declares a patient 20/40/60s schedule; the runner must forward it so the
    # fetcher doesn't re-trip the 429 with its ~1s CI default.
    conn = FakeConn(make_source(id="gdelt"), raw_returns=[])
    pool = FakePool(conn)
    fetcher = _RecordingFetcher({"articles": []})

    await run_source("gdelt", pool, fetcher=fetcher, embed=False, max_pages=1)

    assert fetcher.kwargs["wait_min"] == 20.0
    assert fetcher.kwargs["wait_max"] == 60.0
    assert fetcher.kwargs["wait_multiplier"] == 20.0
    assert fetcher.kwargs["max_attempts"] == 4


async def test_ordinary_source_gets_default_backoff():
    # A source that declares no retry hints passes the neutral defaults (multiplier 1.0, no
    # min/max override) — so only GDELT gets the patient schedule.
    conn = FakeConn(make_source(id="usaspending"), raw_returns=[])
    pool = FakePool(conn)
    fetcher = _RecordingFetcher(make_response([]))

    await run_source("usaspending", pool, fetcher=fetcher, embed=False, max_pages=1)

    assert fetcher.kwargs["wait_min"] is None
    assert fetcher.kwargs["wait_max"] is None
    assert fetcher.kwargs["wait_multiplier"] == 1.0
    assert fetcher.kwargs["max_attempts"] is None
