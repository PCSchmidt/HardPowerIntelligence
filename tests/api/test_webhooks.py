"""Lemon Squeezy webhook tests (D050, D075).

Signature verification + subscription persistence. The DB pool is a fake that
captures executed SQL/args (no real DB), set on app.state for the persistence cases.
"""
import hashlib
import hmac
import json
import uuid

import pytest
from app.main import app
from app.settings import api_settings
from fastapi.testclient import TestClient

client = TestClient(app)

_URL = "/v1/webhooks/lemon-squeezy"
_SECRET = "whsec_test"


def _sign(body: bytes) -> str:
    return hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()


def _post(payload: dict):
    body = json.dumps(payload).encode()
    return client.post(_URL, content=body, headers={"X-Signature": _sign(body)})


# ── Fake DB pool capturing execute() calls ───────────────────────────────────
class FakeConn:
    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []

    async def execute(self, sql, *args):
        self.calls.append((sql, args))
        return "INSERT 0 1"


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


@pytest.fixture
def fake_pool(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(api_settings, "lemonsqueezy_webhook_secret", _SECRET)
    monkeypatch.setattr(app.state, "pool", FakePool(conn), raising=False)
    return conn


# ── Signature / config ───────────────────────────────────────────────────────
def test_webhook_unconfigured_acknowledges(monkeypatch):
    monkeypatch.setattr(api_settings, "lemonsqueezy_webhook_secret", "")
    resp = client.post(_URL, content=b"{}", headers={"X-Signature": "anything"})
    assert resp.status_code == 200
    assert resp.json() == {"received": True}


def test_webhook_bad_signature_rejected(monkeypatch):
    monkeypatch.setattr(api_settings, "lemonsqueezy_webhook_secret", _SECRET)
    resp = client.post(_URL, content=b'{"meta":{}}', headers={"X-Signature": "deadbeef"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_signature"


# ── Persistence ──────────────────────────────────────────────────────────────
def _sub_payload(event_name: str, user_id: str, status: str, **attrs):
    return {
        "meta": {"event_name": event_name, "custom_data": {"user_id": user_id}},
        "data": {
            "id": "sub_123",
            "attributes": {"customer_id": 99, "status": status, **attrs},
        },
    }


def test_created_upserts_pro(fake_pool):
    uid = str(uuid.uuid4())
    resp = _post(
        _sub_payload("subscription_created", uid, "on_trial", renews_at="2026-07-01T00:00:00Z")
    )
    assert resp.status_code == 200
    assert len(fake_pool.calls) == 1
    sql, args = fake_pool.calls[0]
    assert "INSERT INTO subscriptions" in sql and "ON CONFLICT (user_id)" in sql
    # args: user_id, ls_customer_id, ls_subscription_id, status, period_end, cancelled_at
    assert args[0] == uuid.UUID(uid)
    assert args[1] == "99"            # ls_customer_id (stringified)
    assert args[2] == "sub_123"       # ls_subscription_id
    assert args[3] == "trialing"      # on_trial → trialing
    assert args[5] is None            # not cancelled → cancelled_at is None


def test_active_status_maps(fake_pool):
    resp = _post(_sub_payload("subscription_updated", str(uuid.uuid4()), "active"))
    assert resp.status_code == 200
    assert fake_pool.calls[0][1][3] == "active"


def test_past_due_maps(fake_pool):
    _post(_sub_payload("subscription_updated", str(uuid.uuid4()), "unpaid"))
    assert fake_pool.calls[0][1][3] == "past_due"


def test_cancelled_event_sets_cancelled(fake_pool):
    resp = _post(
        _sub_payload(
            "subscription_cancelled", str(uuid.uuid4()), "active",
            ends_at="2026-07-01T00:00:00Z",
        )
    )
    assert resp.status_code == 200
    args = fake_pool.calls[0][1]
    assert args[3] == "cancelled"     # forced cancelled by event
    assert args[5] is not None        # cancelled_at set


def test_non_subscription_event_ignored(fake_pool):
    resp = _post(
        {"meta": {"event_name": "order_created", "custom_data": {"user_id": str(uuid.uuid4())}}}
    )
    assert resp.status_code == 200
    assert fake_pool.calls == []      # nothing persisted


def test_missing_user_acknowledged_not_persisted(fake_pool):
    resp = _post({"meta": {"event_name": "subscription_created", "custom_data": {}}})
    assert resp.status_code == 200
    assert fake_pool.calls == []


def test_non_uuid_user_acknowledged_not_persisted(fake_pool):
    resp = _post(_sub_payload("subscription_created", "not-a-uuid", "active"))
    assert resp.status_code == 200
    assert fake_pool.calls == []


def test_stores_customer_portal_url(fake_pool):
    url = "https://hpi.lemonsqueezy.com/billing?expires=123&signature=abc"
    resp = _post(
        _sub_payload(
            "subscription_created", str(uuid.uuid4()), "active",
            urls={"customer_portal": url},
        )
    )
    assert resp.status_code == 200
    args = fake_pool.calls[0][1]
    assert args[6] == url          # customer_portal_url is the 7th bind arg (D080)


def test_missing_urls_persists_null_portal(fake_pool):
    resp = _post(_sub_payload("subscription_updated", str(uuid.uuid4()), "active"))
    assert resp.status_code == 200
    assert fake_pool.calls[0][1][6] is None
