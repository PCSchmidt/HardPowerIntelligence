"""Shared asyncpg connection pool factory (D043).

Single source of truth for pool creation. Imported by FastAPI (lifespan-managed)
and by worker/script code. Strips the SQLAlchemy-style ``+asyncpg`` suffix that the
DSN carries for tooling compatibility, since asyncpg wants a bare ``postgres://`` URL.
"""
from __future__ import annotations

import asyncpg

from engine.settings import settings


def normalize_dsn(url: str) -> str:
    """Convert a ``postgresql+asyncpg://`` DSN into the bare form asyncpg expects."""
    return url.replace("+asyncpg", "")


async def create_pool(
    dsn: str | None = None,
    *,
    min_size: int = 1,
    max_size: int = 10,
    **kwargs,
) -> asyncpg.Pool:
    """Create an asyncpg pool from the given DSN (defaults to ``settings.database_url``)."""
    resolved = normalize_dsn(dsn or settings.database_url)
    if not resolved:
        raise RuntimeError("DATABASE_URL is not configured")
    return await asyncpg.create_pool(resolved, min_size=min_size, max_size=max_size, **kwargs)
