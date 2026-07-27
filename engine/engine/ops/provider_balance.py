"""Provider credit-balance probe for the runway check (D156, D158).

The 2026-07-24 dark was OpenRouter running out of credits with no warning (D155). This measures the
remaining balance so `run_health` can (a) warn BEFORE the primary lane runs dry, and (b) diagnose a
0-brief day as billing exhaustion rather than a code/data fault.

OpenRouter enforces TWO independent spend ceilings, and the *lower* one binds (D158):
  - the ACCOUNT credit balance   (GET /api/v1/credits → total_credits − total_usage), and
  - the API KEY's own total limit (GET /api/v1/key → limit_remaining).
The 2026-07-27 dark was the key hitting its $20 total limit (403 "Key limit exceeded") while the
account still showed ~$17 credits — so probing credits ALONE reported "healthy" while every call
403'd. We now report the binding minimum of the two, and name which one is binding in `detail`.

Fireworks (the cross-provider last-resort) has no public balance endpoint, but it needs none here:
its health is observable through *outcomes* — if OpenRouter is dry and briefs still published, the
backstop served (`running_on_backstop`); if dry and nothing published, both failed
(`billing_exhausted`). So the OpenRouter balance × publish outcome tells the whole story.

HTTP lives only in `fetch_openrouter_balance`; the parsers are pure and unit-tested. A probe failure
NEVER raises — it returns `reachable=False` so the health run continues regardless."""
from __future__ import annotations

from dataclasses import dataclass

import httpx

_OPENROUTER_CREDITS_URL = "https://openrouter.ai/api/v1/credits"
_OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"
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


def parse_openrouter_key_remaining(payload: dict) -> float | None:
    """Remaining spend on the KEY's own total limit (GET /api/v1/key → data.limit_remaining).

    None when the key is uncapped (limit is null → limit_remaining null) or the shape is
    unexpected — i.e. 'no key-level constraint known', so it never tightens the effective balance."""
    try:
        rem = payload["data"].get("limit_remaining")
        return float(rem) if rem is not None else None
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def _binding_remaining(
    account: float | None, key_remaining: float | None
) -> tuple[float | None, str]:
    """The lower of account credits and key-limit remaining, plus a detail naming what binds."""
    if account is None and key_remaining is None:
        return None, "unparseable balance payload"
    if key_remaining is None:
        return account, f"account ${account:,.2f} (key uncapped)"
    if account is None:
        return key_remaining, f"key limit ${key_remaining:,.2f} remaining"
    if key_remaining <= account:
        return key_remaining, f"key limit ${key_remaining:,.2f} of key cap binds (account ${account:,.2f})"
    return account, f"account ${account:,.2f} binds (key ${key_remaining:,.2f})"


async def _get_json(client: httpx.AsyncClient, url: str, api_key: str) -> dict | None:
    """GET a JSON endpoint; None on any non-200 or error (a partial probe must not crash health)."""
    try:
        resp = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
        return resp.json() if resp.status_code == 200 else None
    except Exception:  # noqa: BLE001
        return None


async def fetch_openrouter_balance(
    api_key: str, *, client: httpx.AsyncClient | None = None
) -> ProviderBalance:
    if not api_key:
        return ProviderBalance("openrouter", reachable=False, remaining_usd=None, detail="no API key")
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=_TIMEOUT_SECONDS)
    try:
        credits_payload = await _get_json(client, _OPENROUTER_CREDITS_URL, api_key)
        key_payload = await _get_json(client, _OPENROUTER_KEY_URL, api_key)
        if credits_payload is None and key_payload is None:
            return ProviderBalance(
                "openrouter", reachable=False, remaining_usd=None, detail="both balance probes failed"
            )
        account = parse_openrouter_credits(credits_payload) if credits_payload else None
        key_remaining = parse_openrouter_key_remaining(key_payload) if key_payload else None
        remaining, detail = _binding_remaining(account, key_remaining)
        return ProviderBalance("openrouter", reachable=True, remaining_usd=remaining, detail=detail)
    except Exception as exc:  # noqa: BLE001 — a probe failure must never crash the health run
        return ProviderBalance("openrouter", reachable=False, remaining_usd=None, detail=str(exc)[:120])
    finally:
        if owns_client:
            await client.aclose()
