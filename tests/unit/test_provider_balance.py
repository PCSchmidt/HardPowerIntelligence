"""OpenRouter balance probe (D156/D158). Pure parse + HTTP paths via httpx.MockTransport.

D158: the probe reads BOTH the account credits (/api/v1/credits) and the key's own total limit
(/api/v1/key) and reports the binding minimum — the 2026-07-27 dark was the key cap at $0 while the
account still had ~$17, which a credits-only probe called "healthy"."""
import httpx
import pytest

from engine.ops.provider_balance import (
    fetch_openrouter_balance,
    parse_openrouter_credits,
    parse_openrouter_key_remaining,
)


class TestParseOpenRouterCredits:
    def test_remaining_is_credits_minus_usage(self):
        assert parse_openrouter_credits({"data": {"total_credits": 10.0, "total_usage": 3.5}}) == 6.5

    def test_missing_keys_returns_none(self):
        assert parse_openrouter_credits({}) is None
        assert parse_openrouter_credits({"data": {"total_credits": 10}}) is None

    def test_bad_types_returns_none(self):
        assert parse_openrouter_credits({"data": {"total_credits": "x", "total_usage": 1}}) is None


class TestParseOpenRouterKeyRemaining:
    def test_reads_limit_remaining(self):
        assert parse_openrouter_key_remaining({"data": {"limit": 20, "limit_remaining": 0.0}}) == 0.0
        assert parse_openrouter_key_remaining({"data": {"limit_remaining": 7.5}}) == 7.5

    def test_uncapped_key_is_none(self):
        # limit null → limit_remaining null → 'no key-level constraint', never tightens the balance.
        assert parse_openrouter_key_remaining({"data": {"limit": None, "limit_remaining": None}}) is None

    def test_missing_or_bad_shape_is_none(self):
        assert parse_openrouter_key_remaining({}) is None
        assert parse_openrouter_key_remaining({"data": {"limit_remaining": "x"}}) is None


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _router(*, credits=None, key=None, status=200):
    """MockTransport handler that routes by endpoint path."""
    def handler(req):
        assert req.headers["Authorization"] == "Bearer k"
        if req.url.path.endswith("/credits"):
            return httpx.Response(status, json=credits if credits is not None else {})
        if req.url.path.endswith("/key"):
            return httpx.Response(status, json=key if key is not None else {})
        return httpx.Response(404, json={})
    return handler


@pytest.mark.asyncio
class TestFetchOpenRouterBalance:
    async def test_no_key_is_unreachable_not_a_crash(self):
        b = await fetch_openrouter_balance("")
        assert b.reachable is False and b.remaining_usd is None

    async def test_uncapped_key_reports_account_balance(self):
        async with _client(_router(
            credits={"data": {"total_credits": 12.0, "total_usage": 11.5}},
            key={"data": {"limit": None, "limit_remaining": None}},
        )) as c:
            b = await fetch_openrouter_balance("k", client=c)
        assert b.reachable is True and b.remaining_usd == 0.5 and "account" in b.detail

    async def test_key_cap_binds_below_account(self):
        # The 2026-07-27 scenario: account healthy ($16.96) but the key limit is spent ($0).
        async with _client(_router(
            credits={"data": {"total_credits": 528.0, "total_usage": 511.04}},
            key={"data": {"limit": 20, "limit_remaining": 0.0}},
        )) as c:
            b = await fetch_openrouter_balance("k", client=c)
        assert b.reachable is True
        assert b.remaining_usd == 0.0            # the KEY cap binds, not the ~$17 account credit
        assert "key" in b.detail.lower()

    async def test_unparseable_both_is_reachable_but_unknown(self):
        async with _client(_router(credits={"nope": 1}, key={"nope": 1})) as c:
            b = await fetch_openrouter_balance("k", client=c)
        assert b.reachable is True and b.remaining_usd is None

    async def test_both_probes_non_200_is_unreachable(self):
        async with _client(_router(status=402)) as c:
            b = await fetch_openrouter_balance("k", client=c)
        assert b.reachable is False and b.remaining_usd is None

    async def test_network_exception_is_swallowed(self):
        def handler(req):
            raise httpx.ConnectError("boom")

        async with _client(handler) as c:
            b = await fetch_openrouter_balance("k", client=c)
        assert b.reachable is False and b.remaining_usd is None
