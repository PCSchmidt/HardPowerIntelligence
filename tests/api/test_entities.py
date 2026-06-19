"""Tests for the entity endpoints (T3.4, D091).

Pure builders (the chip summary + the Entity 360 shaping, including the private flag and the
cross-desk convergence signal) are unit-tested directly; the endpoint's not-found path is tested
through the app with the auth + pool dependencies overridden.
"""
from contextlib import asynccontextmanager

from fastapi.testclient import TestClient

from app.deps import Principal, get_pool, get_principal
from app.main import app
from app.routers.entities import entity_detail, entity_summary


class TestEntitySummary:
    def test_public_company_has_ticker_and_not_private(self):
        out = entity_summary({"id": "e1", "name": "Lockheed Martin", "type": "company", "ticker": "LMT"})
        assert out == {"id": "e1", "name": "Lockheed Martin", "type": "company",
                       "ticker": "LMT", "is_private": False}

    def test_minted_entity_without_ticker_is_private(self):
        out = entity_summary({"id": "e2", "name": "Anduril Industries", "type": "company", "ticker": None})
        assert out["ticker"] is None
        assert out["is_private"] is True


class TestEntityDetail:
    def _appearance(self, desk, date="2026-06-19"):
        return {"brief_id": "b1", "desk": desk, "date": date,
                "headline": "Award", "item_type": "award"}

    def test_derives_ticker_and_identifiers(self):
        out = entity_detail(
            {"id": "e1", "name": "NuScale Power", "type": "company"},
            [{"id_type": "ticker", "id_value": "SMR"}, {"id_type": "cik", "id_value": "0001822966"}],
            [self._appearance("energy")],
        )
        assert out["ticker"] == "SMR"
        assert out["is_private"] is False
        assert {"type": "cik", "value": "0001822966"} in out["identifiers"]

    def test_private_when_no_ticker_identifier(self):
        out = entity_detail(
            {"id": "e2", "name": "Anduril Industries", "type": "company"},
            [{"id_type": "uei", "id_value": "ABC123"}],
            [self._appearance("defense")],
        )
        assert out["ticker"] is None
        assert out["is_private"] is True

    def test_convergence_when_entity_spans_multiple_desks(self):
        out = entity_detail(
            {"id": "e3", "name": "Constellation Energy", "type": "company"},
            [{"id_type": "ticker", "id_value": "CEG"}],
            [self._appearance("energy"), self._appearance("ai"), self._appearance("energy")],
        )
        assert out["desks"] == ["ai", "energy"]   # distinct + sorted
        assert out["convergence"] is True

    def test_single_desk_is_not_convergence(self):
        out = entity_detail(
            {"id": "e4", "name": "Boeing", "type": "company"},
            [{"id_type": "ticker", "id_value": "BA"}],
            [self._appearance("defense")],
        )
        assert out["desks"] == ["defense"]
        assert out["convergence"] is False

    def test_desk_string_not_iterated_as_chars(self):
        # Regression: briefs.desk is a scalar string; it must not be split into characters.
        out = entity_detail({"id": "e5", "name": "X", "type": "company"}, [],
                            [self._appearance("defense")])
        assert out["desks"] == ["defense"]


class _FakeConn:
    def __init__(self, entity_row):
        self._entity_row = entity_row

    async def fetchrow(self, *args):
        return self._entity_row

    async def fetch(self, *args):
        return []


class _FakePool:
    def __init__(self, entity_row):
        self._entity_row = entity_row

    @asynccontextmanager
    async def acquire(self):
        yield _FakeConn(self._entity_row)


def _override(entity_row):
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id="u1", email="a@b.com", is_admin=False, tier="free"
    )
    app.dependency_overrides[get_pool] = lambda: _FakePool(entity_row)


def teardown_function():
    app.dependency_overrides.clear()


def test_unknown_entity_returns_404():
    _override(entity_row=None)
    client = TestClient(app)
    resp = client.get("/v1/entities/11111111-1111-1111-1111-111111111111")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_known_entity_returns_detail():
    _override(entity_row={"id": "e1", "name": "Lockheed Martin", "type": "company"})
    client = TestClient(app)
    resp = client.get("/v1/entities/11111111-1111-1111-1111-111111111111")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Lockheed Martin"
    assert body["is_private"] is True   # _FakeConn returns no identifiers → no ticker
    assert body["appearances"] == []
