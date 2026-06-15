"""create_pool retry behavior (D057).

Spec (engine/db.py):
- transient connection failures (DNS getaddrinfo, connection refused/reset) are
  retried with backoff, then succeed or exhaust;
- a non-transient error (e.g. asyncpg auth failure) raises immediately, no retry;
- a missing DSN raises RuntimeError without touching the network.
"""
import socket

import asyncpg
import pytest

from engine import db


@pytest.fixture
def patch_asyncpg(monkeypatch):
    """Replace asyncpg.create_pool with a scripted fake; return its call counter."""
    calls = {"n": 0}

    def make(side_effects):
        async def fake_create_pool(*args, **kwargs):
            i = calls["n"]
            calls["n"] += 1
            effect = side_effects[min(i, len(side_effects) - 1)]
            if isinstance(effect, Exception):
                raise effect
            return effect

        monkeypatch.setattr(asyncpg, "create_pool", fake_create_pool)
        return calls

    return make


async def test_succeeds_first_try(patch_asyncpg):
    calls = patch_asyncpg(["POOL"])
    pool = await db.create_pool("postgresql://u:p@h/db", wait_min=0, wait_max=0)
    assert pool == "POOL"
    assert calls["n"] == 1


async def test_retries_dns_failure_then_succeeds(patch_asyncpg):
    calls = patch_asyncpg([socket.gaierror(11001, "getaddrinfo failed"), "POOL"])
    pool = await db.create_pool("postgresql://u:p@h/db", wait_min=0, wait_max=0)
    assert pool == "POOL"
    assert calls["n"] == 2  # one retry


async def test_retries_connection_refused_then_succeeds(patch_asyncpg):
    calls = patch_asyncpg([ConnectionRefusedError("refused"), "POOL"])
    pool = await db.create_pool("postgresql://u:p@h/db", wait_min=0, wait_max=0)
    assert pool == "POOL"
    assert calls["n"] == 2


async def test_exhausts_retries_and_raises(patch_asyncpg):
    calls = patch_asyncpg([socket.gaierror("dns down")])
    with pytest.raises(socket.gaierror):
        await db.create_pool("postgresql://u:p@h/db", max_attempts=3, wait_min=0, wait_max=0)
    assert calls["n"] == 3  # max_attempts, no more


async def test_auth_error_is_not_retried(patch_asyncpg):
    # asyncpg auth failure is not a transient connection error → fail fast.
    calls = patch_asyncpg([asyncpg.InvalidPasswordError("bad password")])
    with pytest.raises(asyncpg.InvalidPasswordError):
        await db.create_pool("postgresql://u:p@h/db", wait_min=0, wait_max=0)
    assert calls["n"] == 1  # no retry on a deterministic auth error


async def test_missing_dsn_raises_without_network(monkeypatch):
    # No DSN → RuntimeError before any asyncpg call.
    monkeypatch.setattr(db.settings, "database_url", "")

    async def boom(*a, **k):
        raise AssertionError("asyncpg.create_pool should not be called")

    monkeypatch.setattr(asyncpg, "create_pool", boom)
    with pytest.raises(RuntimeError, match="DATABASE_URL is not configured"):
        await db.create_pool()


class TestTransientRetry:
    """transient_retry decorator for DB ops on a possibly-stale pooled connection (D069)."""

    async def test_retries_dns_then_succeeds(self):
        calls = {"n": 0}

        @db.transient_retry(wait_min=0, wait_max=0)
        async def op():
            calls["n"] += 1
            if calls["n"] < 3:
                raise socket.gaierror(11001, "getaddrinfo failed")
            return "ok"

        assert await op() == "ok"
        assert calls["n"] == 3  # two retries, then success

    async def test_exhausts_and_reraises(self):
        calls = {"n": 0}

        @db.transient_retry(max_attempts=3, wait_min=0, wait_max=0)
        async def op():
            calls["n"] += 1
            raise ConnectionResetError("reset")

        with pytest.raises(ConnectionResetError):
            await op()
        assert calls["n"] == 3

    async def test_non_transient_not_retried(self):
        calls = {"n": 0}

        @db.transient_retry(wait_min=0, wait_max=0)
        async def op():
            calls["n"] += 1
            raise asyncpg.InvalidPasswordError("bad password")

        with pytest.raises(asyncpg.InvalidPasswordError):
            await op()
        assert calls["n"] == 1  # deterministic error → fail fast
