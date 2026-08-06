"""Configuration read from standard environment variables (ADR-0009).

No secrets have default values here. No ORM or database driver is
configured — that remains an open, unapproved implementation decision.
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


def get_settings() -> Settings:
    """Read settings freshly from the environment on every call.

    Deliberately not cached as a module-level singleton.
    """
    return Settings(
        environment=os.environ.get("TRADING_AI_ENVIRONMENT", "development"),
        log_level=os.environ.get("TRADING_AI_LOG_LEVEL", "INFO"),
        host=os.environ.get("TRADING_AI_HOST", "127.0.0.1"),
        port=int(os.environ.get("TRADING_AI_PORT", "8000")),
        debug=_get_bool("TRADING_AI_DEBUG", False),
    )
