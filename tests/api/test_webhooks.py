import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.main import app
from app.settings import api_settings

client = TestClient(app)

_URL = "/v1/webhooks/lemon-squeezy"


def test_webhook_unconfigured_acknowledges(monkeypatch):
    monkeypatch.setattr(api_settings, "lemonsqueezy_webhook_secret", "")
    resp = client.post(_URL, content=b"{}", headers={"X-Signature": "anything"})
    assert resp.status_code == 200
    assert resp.json() == {"received": True}


def test_webhook_bad_signature_rejected(monkeypatch):
    monkeypatch.setattr(api_settings, "lemonsqueezy_webhook_secret", "secret")
    resp = client.post(_URL, content=b'{"meta":{}}', headers={"X-Signature": "deadbeef"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_signature"


def test_webhook_valid_signature_accepted(monkeypatch):
    secret = "secret"
    monkeypatch.setattr(api_settings, "lemonsqueezy_webhook_secret", secret)
    body = json.dumps(
        {"meta": {"event_name": "subscription_created", "custom_data": {"user_id": "u-1"}}}
    ).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    resp = client.post(_URL, content=body, headers={"X-Signature": signature})
    assert resp.status_code == 200
    assert resp.json() == {"received": True}
