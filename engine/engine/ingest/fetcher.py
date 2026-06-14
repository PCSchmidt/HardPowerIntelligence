"""HTTP fetch layer for ingestion — retry/backoff over a hostile network.

A thin wrapper around ``httpx.AsyncClient`` that the runner uses to call source
APIs. Retries are bounded and target *transient* failures only:

- transport errors (DNS, connection reset, read timeout) — we hit intermittent
  DNS flakiness against pooled hosts in deploy, so the network is assumed hostile;
- HTTP 429 (rate limited) and 5xx (server) — back off and retry.

A 4xx other than 429 is a *deterministic* client error (bad request, auth) — it
is raised immediately, not retried, so a broken adapter fails fast instead of
hammering the source.
"""
from __future__ import annotations

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

log = structlog.get_logger()

_DEFAULT_TIMEOUT = 30.0
_DEFAULT_MAX_ATTEMPTS = 4


class RetryableHTTPError(Exception):
    """A transient HTTP status (429/5xx) worth retrying."""

    def __init__(self, status_code: int, url: str):
        self.status_code = status_code
        self.url = url
        super().__init__(f"retryable HTTP {status_code} from {url}")


class HttpFetcher:
    """Fetch-and-parse-JSON with bounded exponential-backoff retries."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
        timeout: float = _DEFAULT_TIMEOUT,
        wait_min: float = 1.0,
        wait_max: float = 20.0,
    ):
        self._client = client
        self._max_attempts = max_attempts
        self._timeout = timeout
        self._wait_min = wait_min   # backoff bounds (tests set these to 0)
        self._wait_max = wait_max

    async def fetch_json(
        self,
        method: str,
        url: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> dict:
        """Issue one logical request (with retries) and return the JSON body.

        Retries transport errors, 429, and 5xx with exponential backoff; raises
        on non-retryable 4xx immediately and after the final retry attempt.
        """

        @retry(
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential(multiplier=1, min=self._wait_min, max=self._wait_max),
            retry=retry_if_exception_type(
                (httpx.TransportError, RetryableHTTPError)
            ),
            reraise=True,
        )
        async def _do() -> dict:
            resp = await self._client.request(
                method.upper(),
                url,
                json=json,
                params=params,
                headers=headers,
                timeout=self._timeout,
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                log.warning(
                    "fetch_retryable", url=url, status=resp.status_code
                )
                raise RetryableHTTPError(resp.status_code, url)
            resp.raise_for_status()  # non-retryable 4xx → raise now
            return resp.json()

        return await _do()
