"""Lemon Squeezy webhook receiver (D050).

Gate 6 scope: verify the HMAC signature and acknowledge. Full subscription-state
persistence (create/update/cancel rows in ``subscriptions``) is wired in Gate 7/8
once the test-mode product and webhook secret exist. No Bearer auth — signature only.
"""
from __future__ import annotations

import hashlib
import hmac
import json

import structlog
from fastapi import APIRouter, Request

from app.errors import APIError
from app.settings import api_settings

log = structlog.get_logger()

router = APIRouter()


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
    user_id = (meta.get("custom_data") or {}).get("user_id")

    # Gate 6 stub: events are logged, not yet persisted to `subscriptions`.
    log.info("ls_webhook_received", event_name=event_name, user_id=user_id)
    return {"received": True}
