"""ASGI application entrypoint.

Only wires the transport layer together (ADR-0002): no business
entities, no repositories, no LLM/queue access here. Database access
is limited to infrastructure wiring (engine/session lifecycle) — no
business queries are issued from this module.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from trading_ai.api.routes.health import router as health_router
from trading_ai.api.routes.ready import router as ready_router
from trading_ai.api.routes.watchlist import register_watchlist_exception_handlers
from trading_ai.api.routes.watchlist import router as watchlist_router
from trading_ai.config import get_settings
from trading_ai.infrastructure.database.engine import create_database_engine
from trading_ai.infrastructure.database.session import create_session_factory
from trading_ai.logging import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create the database engine on startup *if configured*, dispose it on shutdown.

    The engine is not created at import time (see
    `trading_ai.infrastructure.database.engine`). If
    `TRADING_AI_DATABASE_URL` is not set, no engine is created at
    all — `app.state.db_engine` is left as `None`, a safe static
    message is logged (no variable values, nothing to leak), and the
    application still starts and serves `/health`. `/ready` handles a
    `None` engine explicitly (see `trading_ai.api.routes.ready`).
    """
    settings = get_settings()

    engine = None
    if settings.database_url is not None:
        engine = create_database_engine(settings.database_url)
        app.state.db_session_factory = create_session_factory(engine)
    else:
        logger.warning(
            "TRADING_AI_DATABASE_URL is not set; database features are disabled."
        )
        app.state.db_session_factory = None

    app.state.db_engine = engine
    try:
        yield
    finally:
        if engine is not None:
            await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="AI Trading Assistant Platform",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(health_router)
    app.include_router(ready_router)
    app.include_router(watchlist_router)
    register_watchlist_exception_handlers(app)
    return app


app = create_app()
