"""Async SQLAlchemy engine factory.

The engine is never created at import time (ADR-0004, ADR-0009): it is
only instantiated by an explicit call, normally from the FastAPI
lifespan (see `trading_ai.main`). Pool configuration is left at
SQLAlchemy's own defaults — no production pool limits are guessed
here; they must come from measurements, not assumptions.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def create_database_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """Create a new async SQLAlchemy engine bound to `database_url`.

    `echo` defaults to False so SQL statements (which may include bind
    parameters) are not logged by default (ADR-0009, §27 redaction).
    """
    return create_async_engine(database_url, echo=echo)
