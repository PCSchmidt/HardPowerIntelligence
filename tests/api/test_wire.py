"""Tests for the Full Wire endpoint (D112) — GET /v1/wire/latest?desk=.

The wire lists the material overflow tied to a desk's latest published brief. Same access as
that brief (signed-in, free tier). Auth + pool deps are overridden; no network.
"""
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

import asyncpg
from fastapi.testclient import TestClient

from app.deps import Principal, get_pool, get_principal
from app.main import app


class _FakeConn:
    def __init__(self, brief_row, wire_rows, fetch_raises=None):
        self._brief_row = brief_row
        self._wire_rows = wire_rows
        self._fetch_raises = fetch_raises

    async def fetchrow(self, *args):
        return self._brief_row

    async def fetch(self, *args):
        if self._fetch_raises is not None:
            raise self._fetch_raises
        return self._wire_rows


class _FakePool:
    def __init__(self, brief_row, wire_rows, fetch_raises=None):
        self._args = (brief_row, wire_rows, fetch_raises)

    @asynccontextmanager
    async def acquire(self):
        yield _FakeConn(*self._args)


def _override(brief_row, wire_rows, fetch_raises=None):
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id="u1", email="a@b.com", is_admin=False, tier="free"
    )
    app.dependency_overrides[get_pool] = lambda: _FakePool(brief_row, wire_rows, fetch_raises)


def teardown_function():
    app.dependency_overrides.clear()


_BRIEF = {
    "id": "b1", "desk": "energy", "date": date(2026, 6, 30),
    "published_at": datetime(2026, 6, 30, 10, tzinfo=timezone.utc),
}


def test_bad_desk_is_400():
    _override(_BRIEF, [])
    resp = TestClient(app).get("/v1/wire/latest?desk=banking")
    assert resp.status_code == 400


def test_no_published_brief_is_404():
    _override(brief_row=None, wire_rows=[])
    resp = TestClient(app).get("/v1/wire/latest?desk=energy")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_returns_wire_items():
    wire_rows = [
        {"source_id": "usaspending", "native_id": "n1", "item_type": "award",
         "headline": "Small DOE grant", "url": "https://a", "materiality_score": 0.51},
        {"source_id": "gdelt", "native_id": "n2", "item_type": "news",
         "headline": "A development", "url": "https://b", "materiality_score": 0.42},
    ]
    _override(_BRIEF, wire_rows)
    resp = TestClient(app).get("/v1/wire/latest?desk=energy")
    assert resp.status_code == 200
    body = resp.json()
    assert body["desk"] == "energy"
    assert body["brief_id"] == "b1"
    assert len(body["items"]) == 2
    assert body["items"][0]["headline"] == "Small DOE grant"
    assert body["items"][0]["source_id"] == "usaspending"


def test_missing_table_degrades_to_empty_wire():
    # Migration not yet applied: the endpoint must return an empty wire, never 500.
    _override(_BRIEF, [], fetch_raises=asyncpg.UndefinedTableError("no brief_wire"))
    resp = TestClient(app).get("/v1/wire/latest?desk=energy")
    assert resp.status_code == 200
    assert resp.json()["items"] == []
