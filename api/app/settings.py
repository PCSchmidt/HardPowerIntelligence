"""API-specific settings.

Shared config (``database_url``, ``supabase_jwt_secret``) lives in ``engine.settings``
and is imported where needed. This holds only what is specific to the HTTP service:
CORS, Lemon Squeezy credentials (D050), and Sentry.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root: api/app/settings.py → parents[2]. Absolute path so `.env` loads
# regardless of the process working directory.
_REPO_ROOT = Path(__file__).resolve().parents[2]


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_REPO_ROOT / ".env", extra="ignore")

    environment: str = "development"
    api_version: str = "1.0.0"

    # Comma-separated list of allowed CORS origins (the Next.js dev/prod URLs).
    cors_allow_origins: str = "http://localhost:3000"

    # Lemon Squeezy (Merchant of Record, D050) — absent in early dev; checkout and
    # webhook handling degrade gracefully when unset (D045).
    lemonsqueezy_api_key: str = ""
    lemonsqueezy_store_id: str = ""
    lemonsqueezy_webhook_secret: str = ""

    sentry_dsn: str = ""

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


api_settings = ApiSettings()
