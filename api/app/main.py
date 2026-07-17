"""hpi-api FastAPI application (D011 — the single data boundary for the frontend)."""
from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.errors import install_exception_handlers
from app.routers import auth, briefs, calendar, entities, graph, health, webhooks
from app.settings import api_settings
from engine.db import create_pool
from engine.settings import settings

log = structlog.get_logger()


def _init_sentry() -> None:
    if not api_settings.sentry_dsn:
        return
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=api_settings.sentry_dsn,
            traces_sample_rate=0.1,
            environment=api_settings.environment,
        )
    except Exception:  # pragma: no cover - sentry is optional in dev
        log.warning("sentry_init_failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = None
    if settings.database_url:
        try:
            pool = await create_pool()
            log.info("db_pool_ready")
        except Exception as exc:  # pragma: no cover - surfaced at startup
            log.error("db_pool_init_failed", error=str(exc))
    else:
        log.warning("database_url_unset")
    app.state.pool = pool
    try:
        yield
    finally:
        if pool is not None:
            await pool.close()


def create_app() -> FastAPI:
    _init_sentry()
    app = FastAPI(title="hpi-api", version=api_settings.api_version, lifespan=lifespan)
    # Pre-set so dependencies never AttributeError before/without lifespan (e.g. in tests).
    app.state.pool = None

    app.add_middleware(
        CORSMiddleware,
        allow_origins=api_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    install_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(auth.router, prefix="/v1")
    app.include_router(briefs.router, prefix="/v1")
    app.include_router(entities.router, prefix="/v1")
    app.include_router(graph.router, prefix="/v1")
    app.include_router(calendar.router, prefix="/v1")
    app.include_router(webhooks.router, prefix="/v1")
    return app


app = create_app()
