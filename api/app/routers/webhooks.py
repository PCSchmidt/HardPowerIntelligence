"""Lemon Squeezy webhook receiver (D050, D075).

Verifies the HMAC signature, then persists subscription state to `subscriptions` so
`resolve_tier` grants Pro to paying users. Idempotent (upsert by user_id), so repeated
deliveries are safe. No Bearer auth — signature only. When the secret is unset it
degrades to accept-and-ignore (D045), so an unconfigured deploy never errors.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime

import asyncpg
import structlog
from fastapi import APIRouter, Request

from app.deps import get_pool
from app.errors import APIError
from app.settings import api_settings

log = structlog.get_logger()

router = APIRouter()

# Lemon Squeezy subscription status → our `subscriptions.status` enum
# (active | past_due | cancelled | trialing). `resolve_tier` grants Pro only for
# active/trialing, so anything else lands the user back on free.
_LS_STATUS_MAP = {
    "on_trial": "trialing",
    "active": "active",
    "past_due": "past_due",
    "unpaid": "past_due",
    "paused": "cancelled",
    "cancelled": "cancelled",
    "expired": "cancelled",
}
_CANCEL_EVENTS = {"subscription_cancelled", "subscription_expired"}


def _parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


async def _persist_subscription(
    pool: asyncpg.Pool,
    user_id: uuid.UUID,
    event_name: str,
    data: dict,
    attrs: dict,
) -> None:
    """Upsert one subscription row per user from a Lemon Squeezy subscription event."""
    status = _LS_STATUS_MAP.get(attrs.get("status"), "active")
    if event_name in _CANCEL_EVENTS:
        status = "cancelled"
    cancelled_at = datetime.now(UTC) if status == "cancelled" else None
    period_end = _parse_dt(attrs.get("renews_at") or attrs.get("ends_at"))
    ls_subscription_id = str(data["id"]) if data.get("id") is not None else None
    ls_customer_id = (
        str(attrs["customer_id"]) if attrs.get("customer_id") is not None else None
    )
    # Signed customer-portal URL for the "Manage subscription" link (D080). Refreshed
    # on every subscription_* event; None on events that omit it (we keep the prior one).
    portal_url = (attrs.get("urls") or {}).get("customer_portal")

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO subscriptions (
                user_id, ls_customer_id, ls_subscription_id, tier, status,
                current_period_end, cancelled_at, source, customer_portal_url, updated_at
            ) VALUES ($1, $2, $3, 'pro', $4, $5, $6, 'lemonsqueezy', $7, now())
            ON CONFLICT (user_id) DO UPDATE SET
                ls_customer_id = EXCLUDED.ls_customer_id,
                ls_subscription_id = EXCLUDED.ls_subscription_id,
                tier = 'pro',
                status = EXCLUDED.status,
                current_period_end = EXCLUDED.current_period_end,
                cancelled_at = EXCLUDED.cancelled_at,
                customer_portal_url = COALESCE(
                    EXCLUDED.customer_portal_url, subscriptions.customer_portal_url
                ),
                updated_at = now()
            """,
            user_id, ls_customer_id, ls_subscription_id, status,
            period_end, cancelled_at, portal_url,
        )


@router.post("/webhooks/lemon-squeezy")
async def lemon_squeezy_webhook(request: Request) -> dict:
    raw = await request.body()
    secret = api_settings.lemonsqueezy_webhook_secret

    if not secret:
        # D045 graceful degradation: not configured yet — acknowledge and ignore.
        log.warning("ls_webhook_unconfigured")
        return {"received": True}

    signature = request.headers.get("X-Signature", "")
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise APIError(400, "invalid_signature", "Lemon Squeezy signature verification failed")

    payload = json.loads(raw or b"{}")
    meta = payload.get("meta", {})
    event_name = meta.get("event_name")
    raw_user_id = (meta.get("custom_data") or {}).get("user_id")

    # Only subscription events carry the state we persist. Acknowledge anything else.
    if not event_name or not event_name.startswith("subscription_"):
        log.info("ls_webhook_ignored", event_name=event_name)
        return {"received": True}

    # No mappable user (e.g. a checkout without custom_data) — ack so LS doesn't retry.
    if not raw_user_id:
        log.warning("ls_webhook_no_user", event_name=event_name)
        return {"received": True}
    try:
        user_id = uuid.UUID(str(raw_user_id))
    except (ValueError, TypeError):
        log.warning("ls_webhook_bad_user", event_name=event_name, user_id=raw_user_id)
        return {"received": True}

    data = payload.get("data") or {}
    attrs = data.get("attributes") or {}
    await _persist_subscription(get_pool(request), user_id, event_name, data, attrs)
    log.info("ls_webhook_persisted", event_name=event_name, user_id=str(user_id))
    return {"received": True}
