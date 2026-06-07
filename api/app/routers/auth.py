"""Auth relay — returns the caller's profile and authoritative subscription tier."""
from __future__ import annotations

import uuid

import asyncpg
from fastapi import APIRouter, Depends

from app.deps import Principal, get_pool, get_principal

router = APIRouter()


@router.get("/auth/me")
async def me(
    principal: Principal = Depends(get_principal),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    async with pool.acquire() as conn:
        sub = await conn.fetchrow(
            "SELECT created_at, current_period_end FROM subscriptions WHERE user_id = $1",
            uuid.UUID(principal.user_id),
        )
    return {
        "user_id": principal.user_id,
        "email": principal.email,
        "tier": principal.tier,
        "subscribed_at": sub["created_at"] if sub else None,
        "current_period_end": sub["current_period_end"] if sub else None,
    }
