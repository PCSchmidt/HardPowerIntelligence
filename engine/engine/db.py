"""Shared asyncpg connection pool factory (D043).

Single source of truth for pool creation. Imported by FastAPI (lifespan-managed)
and by worker/script code. Strips the SQLAlchemy-style ``+asyncpg`` suffix that the
DSN carries for tooling compatibility, since asyncpg wants a bare ``postgres://`` URL.

Pool creation is retried on *transient* connection failures (DNS ``getaddrinfo``
flakiness, connection refused/reset) — the Supabase pooler host has intermittently
failed to resolve from local + CI, and an unattended scheduled run shouldn't die on
a blip that self-heals in seconds (D057). Auth/config errors are not retried.
"""
from __future__ import annotations

import socket

import asyncpg
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from engine.settings import settings

log = structlog.get_logger()

# Transient connectivity failures worth retrying. socket.gaierror covers DNS
# (getaddrinfo failed); OSError covers connection refused/reset/timeouts. asyncpg
# auth/config errors (subclasses of asyncpg.PostgresError) are NOT retried.
_TRANSIENT_CONN_ERRORS = (socket.gaierror, ConnectionError, OSError)

_DEFAULT_MAX_ATTEMPTS = 4


def normalize_dsn(url: str) -> str:
    """Convert a ``postgresql+asyncpg://`` DSN into the bare form asyncpg expects."""
    return url.replace("+asyncpg", "")


async def create_pool(
    dsn: str | None = None,
    *,
    min_size: int = 1,
    max_size: int = 10,
    max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
    wait_min: float = 1.0,
    wait_max: float = 15.0,
    **kwargs,
) -> asyncpg.Pool:
    """Create an asyncpg pool from the given DSN (defaults to ``settings.database_url``).

    Retries transient connection failures with exponential backoff; raises
    immediately on a missing DSN or a non-transient error (e.g. bad password).
    ``wait_min``/``wait_max`` bound the backoff (tests set these to 0).
    """
    resolved = normalize_dsn(dsn or settings.database_url)
    if not resolved:
        raise RuntimeError("DATABASE_URL is not configured")

    @retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=wait_min, max=wait_max),
        retry=retry_if_exception_type(_TRANSIENT_CONN_ERRORS),
        reraise=True,
        before_sleep=lambda rs: log.warning(
            "db_connect_retry",
            attempt=rs.attempt_number,
            error=str(rs.outcome.exception()),
        ),
    )
    async def _connect() -> asyncpg.Pool:
        return await asyncpg.create_pool(
            resolved, min_size=min_size, max_size=max_size, **kwargs
        )

    return await _connect()
