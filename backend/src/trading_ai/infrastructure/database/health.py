"""PostgreSQL readiness check.

Performs a single, safe `SELECT 1` — no schema access, no migrations,
no business tables. Used by the `/ready` endpoint (ADR-0009, §41).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


async def check_database_connection(engine: AsyncEngine) -> None:
    """Raise if the database is not reachable via a trivial query.

    Callers decide how to translate the exception into a response —
    this function does not itself hide or format errors.
    """
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
