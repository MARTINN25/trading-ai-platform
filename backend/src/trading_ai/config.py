"""Configuration read from standard environment variables (ADR-0009).

No secrets have default values here. `TRADING_AI_DATABASE_URL` is
*optional* at settings-load time: importing the application and using
liveness (`GET /health`) must never require it (ADR-0009, §41 —
liveness performs no dependency checks). Only operations that
genuinely need a working database connection (the `/ready` readiness
check when a URL is configured, Alembic migrations) require it
explicitly via `get_required_database_url()`, which fails fast with a
clear, credential-free message instead of silently proceeding with
`None`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _get_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    environment: str
    log_level: str
    host: str
    port: int
    debug: bool
    database_url: str | None


def get_settings() -> Settings:
    """Read settings freshly from the environment on every call.

    Deliberately not cached as a module-level singleton. Never raises
    due to a missing database URL — the application must be
    importable and startable, and `/health` usable, without one.
    """
    return Settings(
        environment=os.environ.get("TRADING_AI_ENVIRONMENT", "development"),
        log_level=os.environ.get("TRADING_AI_LOG_LEVEL", "INFO"),
        host=os.environ.get("TRADING_AI_HOST", "127.0.0.1"),
        port=int(os.environ.get("TRADING_AI_PORT", "8000")),
        debug=_get_bool("TRADING_AI_DEBUG", False),
        database_url=os.environ.get("TRADING_AI_DATABASE_URL") or None,
    )


def get_required_database_url(settings: Settings | None = None) -> str:
    """Return the database URL, or raise a clear, credential-free error.

    Used only where a database connection is actually attempted (the
    readiness check's engine creation, Alembic migrations) — never by
    application import/startup or by `/health`.
    """
    settings = settings if settings is not None else get_settings()
    if settings.database_url is None:
        raise RuntimeError(
            "TRADING_AI_DATABASE_URL is required for this operation "
            "but was not set."
        )
    return settings.database_url
