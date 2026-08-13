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
from fastapi.middleware.cors import CORSMiddleware

from trading_ai.ai.gateway import XAIGateway
from trading_ai.ai.pending_cache import PendingAnalysisCache
from trading_ai.api.routes.evaluations import register_evaluation_exception_handlers
from trading_ai.api.routes.evaluations import router as evaluations_router
from trading_ai.api.routes.health import router as health_router
from trading_ai.api.routes.instruments import register_ai_analysis_exception_handlers
from trading_ai.api.routes.instruments import register_insight_exception_handlers
from trading_ai.api.routes.instruments import register_instruments_exception_handlers
from trading_ai.api.routes.instruments import router as instruments_router
from trading_ai.api.routes.journal import register_journal_exception_handlers
from trading_ai.api.routes.journal import router as journal_router
from trading_ai.api.routes.live_market import router as live_market_router
from trading_ai.api.routes.ready import router as ready_router
from trading_ai.api.routes.watchlist import register_watchlist_exception_handlers
from trading_ai.api.routes.watchlist import router as watchlist_router
from trading_ai.config import get_settings
from trading_ai.infrastructure.database.engine import create_database_engine
from trading_ai.infrastructure.database.session import create_session_factory
from trading_ai.logging import configure_logging
from trading_ai.market_data.gateway import TwelveDataGateway
from trading_ai.market_data.live_manager import LiveMarketManager
from trading_ai.market_data.news_gateway import FinnhubNewsGateway
from trading_ai.market_data.twelve_data_stream import TwelveDataStreamClient

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

    # Same optional-feature pattern as the database above: no key, no
    # gateway, GET /watchlist/quotes reports 503 — nothing else is
    # affected. No pooled resource to dispose (each call opens its own
    # short-lived httpx client), unlike the database engine.
    if settings.market_data_api_key is not None:
        app.state.market_data_gateway = TwelveDataGateway(
            api_key=settings.market_data_api_key
        )
    else:
        logger.warning(
            "TRADING_AI_MARKET_DATA_API_KEY is not set; market data is disabled."
        )
        app.state.market_data_gateway = None

    # Phase 2C.3: one process-local LiveMarketManager (task scope §5/§6
    # — never one per request/browser tab), built only when market data
    # is configured at all, reusing the same gateway constructed above
    # for REST bootstrap/fallback rather than a second instance. When
    # `TRADING_AI_LIVE_STREAMING_ENABLED=false`, `stream_client` stays
    # `None`, which `LiveMarketManager.start()` already treats as
    # "run in REST-poll-only mode" (Phase 2C.2) — no separate feature
    # flag branch is needed here. A missing/disabled key degrades only
    # `GET /instruments/{ticker}/live-stream` (503), never the rest of
    # the application (same optional-feature pattern as the three
    # gateways above); `manager.start()` only schedules a background
    # task and cannot itself raise, so it cannot crash startup either.
    live_market_manager: LiveMarketManager | None = None
    if settings.market_data_api_key is not None:
        stream_client = (
            TwelveDataStreamClient(api_key=settings.market_data_api_key)
            if settings.market_data_live_streaming_enabled
            else None
        )
        live_market_manager = LiveMarketManager(
            stream_client=stream_client,
            quote_gateway=app.state.market_data_gateway,
            poll_interval_seconds=settings.market_data_live_poll_interval_seconds,
        )
        await live_market_manager.start()
    else:
        logger.warning(
            "TRADING_AI_MARKET_DATA_API_KEY is not set; live market streaming is disabled."
        )
    app.state.live_market_manager = live_market_manager

    # Same optional-feature pattern, separate provider/secret (Finnhub,
    # news only): no key, no gateway, GET /instruments/{ticker}/news
    # reports 503 — nothing else is affected.
    if settings.news_api_key is not None:
        app.state.news_gateway = FinnhubNewsGateway(api_key=settings.news_api_key)
    else:
        logger.warning("TRADING_AI_NEWS_API_KEY is not set; instrument news is disabled.")
        app.state.news_gateway = None

    # Same optional-feature pattern, third separate provider/secret
    # (xAI, ADR-0007 §64): no key, no gateway,
    # POST /instruments/{ticker}/analysis reports 503 — nothing else
    # is affected.
    if settings.llm_api_key is not None:
        app.state.ai_gateway = XAIGateway(api_key=settings.llm_api_key, model=settings.llm_model)
    else:
        logger.warning("TRADING_AI_LLM_API_KEY is not set; AI analysis is disabled.")
        app.state.ai_gateway = None

    # Unconditional, unlike the three gateways above: plain in-process
    # memory (`ai/pending_cache.py`), not an external secret-gated
    # provider — always available regardless of which API keys are set.
    app.state.pending_analysis_cache = PendingAnalysisCache()

    try:
        yield
    finally:
        # Stop the manager before disposing the DB engine — no ordering
        # dependency between the two, but shutting down the
        # longer-lived background task first keeps shutdown log output
        # readable. `LiveMarketManager.stop()` cancels its own
        # background task, closes the stream client, and never raises
        # (task scope §5: "no pending task warnings, no zombie
        # reconnect loops").
        if live_market_manager is not None:
            await live_market_manager.stop()
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
    # Origins come from Settings (TRADING_AI_CORS_ORIGINS, default is
    # local-dev only — ADR-0002 §13: production CORS policy is a
    # separate deployment decision, not fixed by this code). Never
    # "*"; no credentials (cookies/auth headers), which this API does
    # not use.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.include_router(health_router)
    app.include_router(ready_router)
    app.include_router(watchlist_router)
    app.include_router(instruments_router)
    app.include_router(live_market_router)
    app.include_router(evaluations_router)
    app.include_router(journal_router)
    register_watchlist_exception_handlers(app)
    register_instruments_exception_handlers(app)
    register_ai_analysis_exception_handlers(app)
    register_insight_exception_handlers(app)
    register_evaluation_exception_handlers(app)
    register_journal_exception_handlers(app)
    return app


app = create_app()
