"""OpenRouter credit-balance probe (D156). Pure parse + HTTP paths via httpx.MockTransport."""
import httpx
import pytest

from engine.ops.provider_balance import fetch_openrouter_balance, parse_openrouter_credits


class TestParseOpenRouterCredits:
    def test_remaining_is_credits_minus_usage(self):
        assert parse_openrouter_credits({"data": {"total_credits": 10.0, "total_usage": 3.5}}) == 6.5

    def test_missing_keys_returns_none(self):
        assert parse_openrouter_credits({}) is None
        assert parse_openrouter_credits({"data": {"total_credits": 10}}) is None

    def test_bad_types_returns_none(self):
        assert parse_openrouter_credits({"data": {"total_credits": "x", "total_usage": 1}}) is None


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
class TestFetchOpenRouterBalance:
    async def test_no_key_is_unreachable_not_a_crash(self):
        b = await fetch_openrouter_balance("")
        assert b.reachable is False and b.remaining_usd is None

    async def test_200_parses_remaining_and_sends_bearer(self):
        def handler(req):
            assert req.headers["Authorization"] == "Bearer k"
            return httpx.Response(200, json={"data": {"total_credits": 12.0, "total_usage": 11.5}})

        async with _client(handler) as c:
            b = await fetch_openrouter_balance("k", client=c)
        assert b.reachable is True and b.remaining_usd == 0.5

    async def test_unparseable_200_is_reachable_but_unknown(self):
        async with _client(lambda req: httpx.Response(200, json={"nope": 1})) as c:
            b = await fetch_openrouter_balance("k", client=c)
        assert b.reachable is True and b.remaining_usd is None

    async def test_non_200_is_unreachable(self):
        async with _client(lambda req: httpx.Response(402, json={})) as c:
            b = await fetch_openrouter_balance("k", client=c)
        assert b.reachable is False and "402" in b.detail

    async def test_network_exception_is_swallowed(self):
        def handler(req):
            raise httpx.ConnectError("boom")

        async with _client(handler) as c:
            b = await fetch_openrouter_balance("k", client=c)
        assert b.reachable is False and b.remaining_usd is None
