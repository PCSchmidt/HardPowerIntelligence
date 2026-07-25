"""Provider credit-balance probe for the runway check (D156).

The 2026-07-24 dark was OpenRouter running out of credits with no warning (D155). This measures the
remaining balance so `run_health` can (a) warn BEFORE the primary lane runs dry, and (b) diagnose a
0-brief day as billing exhaustion rather than a code/data fault.

Only OpenRouter is probed directly — it exposes remaining credits (GET /api/v1/credits). Fireworks
(the cross-provider last-resort) has no public balance endpoint, but it needs none here: its health
is observable through *outcomes* — if OpenRouter is dry and briefs still published, the backstop
served (run_health emits `running_on_backstop`); if OpenRouter is dry and nothing published, both
failed (`billing_exhausted`). So the OpenRouter balance × publish outcome tells the whole story.

HTTP lives only in `fetch_openrouter_balance`; `parse_openrouter_credits` is pure and unit-tested. A
probe failure NEVER raises — it returns `reachable=False` so the health run continues regardless."""
from __future__ import annotations

from dataclasses import dataclass

import httpx

_OPENROUTER_CREDITS_URL = "https://openrouter.ai/api/v1/credits"
_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True)
class ProviderBalance:
    provider: str
    reachable: bool
    remaining_usd: float | None  # None = balance unknown (probe failed or no endpoint)
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "provider": self.provider,
            "reachable": self.reachable,
            "remaining_usd": self.remaining_usd,
            "detail": self.detail,
        }


def parse_openrouter_credits(payload: dict) -> float | None:
    """Remaining USD = total_credits − total_usage. None if the payload shape is unexpected."""
    try:
        data = payload["data"]
        return float(data["total_credits"]) - float(data["total_usage"])
    except (KeyError, TypeError, ValueError):
        return None


async def fetch_openrouter_balance(
    api_key: str, *, client: httpx.AsyncClient | None = None
) -> ProviderBalance:
    if not api_key:
        return ProviderBalance("openrouter", reachable=False, remaining_usd=None, detail="no API key")
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=_TIMEOUT_SECONDS)
    try:
        resp = await client.get(
            _OPENROUTER_CREDITS_URL, headers={"Authorization": f"Bearer {api_key}"}
        )
        if resp.status_code != 200:
            return ProviderBalance(
                "openrouter", reachable=False, remaining_usd=None, detail=f"HTTP {resp.status_code}"
            )
        remaining = parse_openrouter_credits(resp.json())
        return ProviderBalance(
            "openrouter",
            reachable=True,
            remaining_usd=remaining,
            detail="" if remaining is not None else "unparseable credits payload",
        )
    except Exception as exc:  # noqa: BLE001 — a probe failure must never crash the health run
        return ProviderBalance("openrouter", reachable=False, remaining_usd=None, detail=str(exc)[:120])
    finally:
        if owns_client:
            await client.aclose()
