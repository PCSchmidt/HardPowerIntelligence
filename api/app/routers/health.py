"""Health check — no auth, used by Fly.io health probes."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.settings import api_settings

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "version": api_settings.api_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
