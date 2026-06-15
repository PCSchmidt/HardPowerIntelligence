"""HttpFetcher retry/backoff behavior. respx mocks httpx — no real network.

Spec (engine/ingest/fetcher.py):
- 2xx → return parsed JSON.
- transport error, 429, 5xx → retry with backoff, then succeed or exhaust.
- non-retryable 4xx (e.g. 404) → raise immediately, no retry.
"""
import httpx
import pytest
import respx
from engine.ingest.fetcher import HttpFetcher

URL = "https://api.example.test/search/"


def _fetcher(client: httpx.AsyncClient) -> HttpFetcher:
    # Zero backoff so retry tests are instant.
    return HttpFetcher(client, max_attempts=4, wait_min=0, wait_max=0)


@respx.mock
async def test_returns_json_on_200():
    respx.post(URL).mock(return_value=httpx.Response(200, json={"results": [1, 2]}))
    async with httpx.AsyncClient() as c:
        out = await _fetcher(c).fetch_json("POST", URL, json={"q": 1})
    assert out == {"results": [1, 2]}


@respx.mock
async def test_returns_text_when_format_is_text():
    # XML/Atom sources (arXiv) need the raw body, not resp.json().
    xml = '<?xml version="1.0"?><feed><entry/></feed>'
    respx.get(URL).mock(return_value=httpx.Response(200, text=xml))
    async with httpx.AsyncClient() as c:
        out = await _fetcher(c).fetch_json("GET", URL, response_format="text")
    assert out == xml


@respx.mock
async def test_retries_5xx_then_succeeds():
    route = respx.post(URL).mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(503),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    async with httpx.AsyncClient() as c:
        out = await _fetcher(c).fetch_json("POST", URL, json={})
    assert out == {"ok": True}
    assert route.call_count == 3


@respx.mock
async def test_retries_429_then_succeeds():
    route = respx.post(URL).mock(
        side_effect=[httpx.Response(429), httpx.Response(200, json={"ok": 1})]
    )
    async with httpx.AsyncClient() as c:
        out = await _fetcher(c).fetch_json("POST", URL, json={})
    assert out == {"ok": 1}
    assert route.call_count == 2


@respx.mock
async def test_retries_transport_error_then_succeeds():
    route = respx.post(URL).mock(
        side_effect=[httpx.ConnectError("boom"), httpx.Response(200, json={"ok": 1})]
    )
    async with httpx.AsyncClient() as c:
        out = await _fetcher(c).fetch_json("POST", URL, json={})
    assert out == {"ok": 1}
    assert route.call_count == 2


@respx.mock
async def test_404_raises_without_retry():
    route = respx.post(URL).mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as c:
        with pytest.raises(httpx.HTTPStatusError):
            await _fetcher(c).fetch_json("POST", URL, json={})
    assert route.call_count == 1  # deterministic 4xx → no retry


@respx.mock
async def test_exhausts_retries_and_raises():
    route = respx.post(URL).mock(return_value=httpx.Response(503))
    async with httpx.AsyncClient() as c:
        with pytest.raises(Exception):
            await _fetcher(c).fetch_json("POST", URL, json={})
    assert route.call_count == 4  # max_attempts
