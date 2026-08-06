"""Readiness endpoint — checks PostgreSQL availability (ADR-0009, §41).

Deliberately separate from `/health` (liveness): only this endpoint
touches the database, and only via a single safe `SELECT 1`. It never
runs migrations and never creates schema. On failure — including when
`TRADING_AI_DATABASE_URL` is not configured at all — it returns a
controlled, generic response — no connection string, host, username,
SQL exception text, or stack trace is ever included.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncEngine

from trading_ai.infrastructure.database.health import check_database_connection

router = APIRouter()
logger = logging.getLogger(__name__)


def get_database_engine(request: Request) -> AsyncEngine | None:
    """Return the engine created by the lifespan, or `None` if unconfigured.

    Uses `getattr` defensively rather than `request.app.state.db_engine`
    directly, so this stays safe even if lifespan startup has not run
    (e.g. `TestClient` used without the `with` context manager).
    """
    engine = getattr(request.app.state, "db_engine", None)
    if engine is not None:
        assert isinstance(engine, AsyncEngine)
    return engine


async def get_readiness_status(
    engine: Annotated[AsyncEngine | None, Depends(get_database_engine)],
) -> bool:
    """Return whether the database is reachable.

    A missing engine (no `TRADING_AI_DATABASE_URL` configured) and any
    connection failure (refused, auth failure, timeout, driver error,
    ...) are both deliberately treated the same way at this system
    boundary: turned into a controlled "not ready" signal, without
    leaking configuration or exception details upstream.
    """
    if engine is None:
        logger.warning("readiness check failed: TRADING_AI_DATABASE_URL is not set")
        return False
    try:
        await check_database_connection(engine)
    except Exception:
        logger.warning("readiness check failed: database unavailable")
        return False
    return True


@router.get("/ready")
async def get_ready(
    response: Response,
    is_ready: Annotated[bool, Depends(get_readiness_status)],
) -> dict[str, str]:
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable"}
    return {"status": "ok"}
