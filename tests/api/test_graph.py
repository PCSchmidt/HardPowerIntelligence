"""Tests for the convergence graph endpoint (Convergence-graph §2).

Pure builders (edge/node/payload shaping, including desk JSON parsing and the convergence flag) are
unit-tested directly; the endpoint's filter validation + happy path go through the app with the auth +
pool dependencies overridden.
"""
from contextlib import asynccontextmanager

from fastapi.testclient import TestClient

from app.deps import Principal, get_pool, get_principal
from app.main import app
from app.routers.graph import edge_payload, graph_payload, node_payload


class TestEdgePayload:
    def _row(self, **over):
        row = {
            "from_id": "a", "to_id": "b", "confidence": 0.86512, "weight": 2.8934,
            "co_count": 3, "desks": '["ai", "defense", "energy"]', "cross_desk": True,
            "last_seen": "2026-07-16",
        }
        row.update(over)
        return row

    def test_shapes_and_rounds(self):
        out = edge_payload(self._row())
        assert out == {
            "from": "a", "to": "b", "confidence": 0.8651, "weight": 2.8934,
            "co_count": 3, "desks": ["ai", "defense", "energy"], "cross_desk": True,
            "last_seen": "2026-07-16",
        }

    def test_parses_desks_from_json_text(self):
        # asyncpg returns a jsonb sub-access as a JSON string; it must become a list
        assert edge_payload(self._row(desks='["ai", "energy"]'))["desks"] == ["ai", "energy"]

    def test_tolerates_already_parsed_desks(self):
        assert edge_payload(self._row(desks=["defense"]))["desks"] == ["defense"]

    def test_bad_desks_degrades_to_empty(self):
        assert edge_payload(self._row(desks="not json"))["desks"] == []


class TestNodePayload:
    def test_public_multidesk_is_convergence(self):
        out = node_payload({"id": "e1", "name": "Ramaco", "ticker": "METC",
                            "desks": ["energy", "ai", "defense"]})
        assert out == {"id": "e1", "name": "Ramaco", "ticker": "METC",
                       "is_private": False, "desks": ["ai", "defense", "energy"], "convergence": True}

    def test_private_single_desk(self):
        out = node_payload({"id": "e2", "name": "USA Rare Earth", "ticker": None, "desks": ["defense"]})
        assert out["is_private"] is True
        assert out["convergence"] is False

    def test_no_desks(self):
        out = node_payload({"id": "e3", "name": "X", "ticker": "X", "desks": None})
        assert out["desks"] == []
        assert out["convergence"] is False


class TestGraphPayload:
    def test_assembles_meta_counts(self):
        edges = [
            {"from_id": "a", "to_id": "b", "confidence": 0.9, "weight": 4.0, "co_count": 3,
             "desks": ["ai", "energy"], "cross_desk": True, "last_seen": "2026-07-16"},
            {"from_id": "c", "to_id": "d", "confidence": 0.7, "weight": 2.0, "co_count": 2,
             "desks": ["energy"], "cross_desk": False, "last_seen": "2026-07-15"},
        ]
        nodes = [{"id": n, "name": n, "ticker": None, "desks": ["energy"]} for n in "abcd"]
        out = graph_payload(edges, nodes)
        assert out["meta"] == {"node_count": 4, "edge_count": 2, "cross_desk_edges": 1}
        assert len(out["nodes"]) == 4 and len(out["edges"]) == 2

    def test_empty(self):
        out = graph_payload([], [])
        assert out["meta"] == {"node_count": 0, "edge_count": 0, "cross_desk_edges": 0}


class _FakeConn:
    def __init__(self, edge_rows, node_rows):
        self._edge_rows = edge_rows
        self._node_rows = node_rows
        self.calls = 0

    async def fetch(self, *args):
        self.calls += 1
        return self._edge_rows if self.calls == 1 else self._node_rows


class _FakePool:
    def __init__(self, edge_rows, node_rows):
        self._c = _FakeConn(edge_rows, node_rows)

    @asynccontextmanager
    async def acquire(self):
        yield self._c


def _override(edge_rows, node_rows):
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id="u1", email="a@b.com", is_admin=False, tier="free"
    )
    app.dependency_overrides[get_pool] = lambda: _FakePool(edge_rows, node_rows)


def teardown_function():
    app.dependency_overrides.clear()


def test_invalid_desk_rejected():
    _override([], [])
    resp = TestClient(app).get("/v1/graph/convergence?desk=space")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_desk"


def test_happy_path_returns_nodes_and_edges():
    edge_rows = [{
        "from_id": "a", "to_id": "b", "confidence": 0.86, "weight": 2.9, "co_count": 3,
        "desks": '["ai", "defense", "energy"]', "cross_desk": True, "last_seen": "2026-07-16",
    }]
    node_rows = [
        {"id": "a", "name": "Ramaco", "ticker": "METC", "desks": ["ai", "defense", "energy"]},
        {"id": "b", "name": "USA Rare Earth", "ticker": None, "desks": ["defense", "ai"]},
    ]
    _override(edge_rows, node_rows)
    resp = TestClient(app).get("/v1/graph/convergence?cross_desk_only=true&min_confidence=0.5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"] == {"node_count": 2, "edge_count": 1, "cross_desk_edges": 1}
    assert body["edges"][0]["desks"] == ["ai", "defense", "energy"]
    assert {n["name"] for n in body["nodes"]} == {"Ramaco", "USA Rare Earth"}


def test_empty_graph_ok():
    _override([], [])
    resp = TestClient(app).get("/v1/graph/convergence")
    assert resp.status_code == 200
    assert resp.json()["meta"]["edge_count"] == 0
