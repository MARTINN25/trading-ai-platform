"""ASGI application entrypoint.

Only wires the transport layer together (ADR-0002): no business
entities, no repositories, no LLM/queue/database access here.
"""

from __future__ import annotations

from fastapi import FastAPI

from trading_ai.api.routes.health import router as health_router
from trading_ai.config import get_settings
from trading_ai.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="AI Trading Assistant Platform",
        version="0.1.0",
    )
    app.include_router(health_router)
    return app


app = create_app()
