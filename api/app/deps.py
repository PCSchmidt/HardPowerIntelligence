"""Request dependencies: JWT auth, subscription tier, and DB pool access.

Implemented as FastAPI dependencies rather than global ASGI middleware so that
auth-exempt routes (``/health``, the Lemon Squeezy webhook) simply omit the
dependency, and protected routes declare it. Mirrors the conceptual middleware
stack in API_SPEC (auth → tier → admin).
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

import asyncpg
import jwt
from fastapi import Depends, Request
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError

from app.errors import APIError
from engine.settings import settings

# JWKS client for asymmetric (ES256/RS256) Supabase tokens. Lazy + caches the key
# set, so it does not fetch on every request.
_jwks_client: PyJWKClient | None = None


def _jwks() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        url = settings.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
        _jwks_client = PyJWKClient(url)
    return _jwks_client


@dataclass
class Principal:
    user_id: str
    email: str
    is_admin: bool
    tier: str  # "free" | "pro"


def verify_token(token: str, secret: str) -> dict:
    """Verify a Supabase access token (aud='authenticated').

    Modern Supabase (cloud + recent CLI) signs with asymmetric JWT signing keys
    (ES256/RS256) verified via the JWKS endpoint. Legacy/self-hosted setups may use
    the shared HS256 secret. The signing algorithm in the token header decides which.
    """
    alg = jwt.get_unverified_header(token).get("alg", "HS256")
    if alg.startswith(("ES", "RS", "PS")):
        signing_key = _jwks().get_signing_key_from_jwt(token)
        return jwt.decode(token, signing_key.key, algorithms=[alg], audience="authenticated")
    return jwt.decode(token, secret, algorithms=["HS256"], audience="authenticated")


def _extract_is_admin(payload: dict) -> bool:
    if payload.get("is_admin") is True:
        return True
    app_metadata = payload.get("app_metadata") or {}
    return bool(app_metadata.get("is_admin", False))


async def _auth_context(request: Request) -> tuple[str, str, bool]:
    header = request.headers.get("Authorization")
    if not header or not header.startswith("Bearer "):
        raise APIError(401, "missing_token", "Authorization header required")
    token = header.split(" ", 1)[1].strip()

    try:
        # Off the event loop: the JWKS path may do a (cached) network fetch.
        payload = await asyncio.to_thread(verify_token, token, settings.supabase_jwt_secret)
    except (jwt.PyJWTError, PyJWKClientError):
        raise APIError(401, "invalid_token", "Token invalid or expired")

    sub = payload.get("sub")
    if not sub:
        raise APIError(401, "invalid_token", "Token missing subject claim")

    return sub, payload.get("email", ""), _extract_is_admin(payload)


def get_pool(request: Request) -> asyncpg.Pool:
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise APIError(503, "db_unavailable", "Database connection not available")
    return pool


async def resolve_tier(pool: asyncpg.Pool, user_id: str) -> str:
    """Resolve subscription tier. No row, or a non-active/non-trialing row, is 'free'."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT tier, status FROM subscriptions WHERE user_id = $1",
            uuid.UUID(user_id),
        )
    if row and row["tier"] == "pro" and row["status"] in ("active", "trialing"):
        return "pro"
    return "free"


async def get_principal(request: Request) -> Principal:
    user_id, email, is_admin = await _auth_context(request)
    pool = get_pool(request)
    tier = await resolve_tier(pool, user_id)
    return Principal(user_id=user_id, email=email, is_admin=is_admin, tier=tier)


async def require_pro(principal: Principal = Depends(get_principal)) -> Principal:
    if principal.tier != "pro":
        raise APIError(403, "pro_required", "Pro subscription required for this resource")
    return principal


async def require_admin(principal: Principal = Depends(get_principal)) -> Principal:
    if not principal.is_admin:
        raise APIError(403, "admin_required", "Admin access required")
    return principal
