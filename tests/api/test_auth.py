import time

import jwt
from fastapi.testclient import TestClient

from app import deps
from app.deps import _extract_is_admin, verify_token
from app.main import app

client = TestClient(app)

_TEST_SECRET = "x" * 40  # >= 32 bytes; deterministic regardless of .env


def test_missing_token_returns_401():
    resp = client.get("/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "missing_token"


def test_malformed_token_returns_401(monkeypatch):
    monkeypatch.setattr(deps.settings, "supabase_jwt_secret", _TEST_SECRET)
    resp = client.get("/v1/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_token"


def test_non_bearer_header_returns_401():
    resp = client.get("/v1/auth/me", headers={"Authorization": "Basic abc"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "missing_token"


def test_verify_token_roundtrip():
    secret = "test-secret"
    token = jwt.encode(
        {"sub": "user-1", "email": "a@b.com", "aud": "authenticated", "exp": int(time.time()) + 3600},
        secret,
        algorithm="HS256",
    )
    decoded = verify_token(token, secret)
    assert decoded["sub"] == "user-1"
    assert decoded["email"] == "a@b.com"


def test_verify_token_wrong_secret_raises():
    token = jwt.encode(
        {"sub": "user-1", "aud": "authenticated", "exp": int(time.time()) + 3600},
        "right-secret",
        algorithm="HS256",
    )
    try:
        verify_token(token, "wrong-secret")
        raised = False
    except jwt.PyJWTError:
        raised = True
    assert raised


def test_extract_is_admin():
    assert _extract_is_admin({"is_admin": True}) is True
    assert _extract_is_admin({"app_metadata": {"is_admin": True}}) is True
    assert _extract_is_admin({"app_metadata": {}}) is False
    assert _extract_is_admin({}) is False
