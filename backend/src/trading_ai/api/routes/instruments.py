"""Instrument details HTTP endpoint — thin transport layer only (ADR-0002, §17).

`GET /instruments/{ticker}` is a read-only market-data lookup for the
watchlist -> instrument-details navigation. It deliberately does not
depend on the database session/repository at all: unlike `/watchlist`,
this is not a combined persistence+market-data operation (task scope —
see `market_data.use_cases.GetInstrumentDetails`).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from trading_ai.ai.gateway import XAIGateway
from trading_ai.ai.types import (
    AIAnalysisError,
    AIInsufficientDataError,
    AIRateLimitedError,
    AITimeoutError,
)
from trading_ai.ai.use_cases import GenerateInstrumentAnalysis
from trading_ai.market_data.gateway import TwelveDataGateway
from trading_ai.market_data.news_gateway import FinnhubNewsGateway
from trading_ai.market_data.types import (
    InvalidPeriodError,
    InvalidSearchQueryError,
    MarketDataError,
    MarketDataRateLimitedError,
    MarketDataTimeoutError,
    TickerUnsupportedError,
)
from trading_ai.market_data.use_cases import (
    GetInstrumentDetails,
    GetInstrumentNews,
    GetInstrumentPriceHistory,
    SearchInstruments,
)

router = APIRouter()


class InstrumentDetailsResponse(BaseModel):
    """Transport DTO — provider-neutral, never Twelve Data's raw response shape.

    `open`/`high`/`low`/`previous_close`/`volume` are `None`, not a
    guessed `0`, whenever the provider's response didn't include or
    couldn't parse that field (see `gateway._optional_decimal`/
    `_optional_int`).
    """

    ticker: str
    price: Decimal
    change: Decimal
    change_percent: Decimal
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    previous_close: Decimal | None = None
    volume: int | None = None
    as_of: datetime
    source: str


class InstrumentSearchResultResponse(BaseModel):
    """Only the fields the UI actually needs — never Twelve Data's raw
    `/symbol_search` item shape (e.g. `mic_code`/`exchange_timezone`
    aren't carried, task scope §10: "search response не содержит
    лишних provider fields")."""

    ticker: str
    name: str
    exchange: str | None = None
    instrument_type: str | None = None
    currency: str | None = None


class InstrumentSearchResponse(BaseModel):
    """`items` is always capped at a fixed size (task scope §6:
    "максимум 10 результатов") — never provider-controlled pagination.
    An empty `items` list is a valid, non-error response."""

    query: str
    items: list[InstrumentSearchResultResponse]


class InstrumentHistoryPointResponse(BaseModel):
    """Only what the line chart needs — OHLC/volume stay internal to
    `PricePoint` (task scope §5: don't carry fields the UI doesn't use)."""

    timestamp: datetime
    close: Decimal


class InstrumentHistoryResponse(BaseModel):
    """`points` is always chronological ASC (`gateway._parse_history`
    sorts defensively regardless of provider ordering) — never trust
    the caller to re-sort. An empty `points` list is a valid, non-error
    response (task scope §5: "пустой набор данных — контролируемый
    safe response")."""

    ticker: str
    period: str
    source: str
    points: list[InstrumentHistoryPointResponse]


class InstrumentNewsItemResponse(BaseModel):
    """`summary` is `None`, not an invented placeholder, whenever the
    provider didn't return one — never substituted with empty text."""

    id: str
    headline: str
    source: str
    published_at: datetime
    url: str
    summary: str | None = None


class InstrumentNewsResponse(BaseModel):
    """`items` is always newest-first and capped at a fixed size (see
    `news_gateway.FinnhubNewsGateway`) — never provider-controlled
    pagination. An empty `items` list is a valid, non-error response,
    same as an empty `points` list for history."""

    ticker: str
    source: str
    items: list[InstrumentNewsItemResponse]


class InstrumentAnalysisResponse(BaseModel):
    """Provider-neutral structured AI result (task scope §4). Never
    BUY/SELL/HOLD/target-price content — enforced by the gateway's
    fixed prompt plus local validation (`ai/gateway.py`), not just
    documented here. `disclaimer` is always the same fixed text."""

    ticker: str
    generated_at: datetime
    summary: str
    price_context: str
    news_context: str
    risks: list[str]
    disclaimer: str
    source: str


def get_market_data_gateway(request: Request) -> TwelveDataGateway:
    """Return the gateway created by the lifespan, or fail controlled.

    Duplicated (not imported) from `api.routes.watchlist`: this route
    module has no other reason to depend on the watchlist route module,
    and the dependency itself is a few lines reading `app.state`.
    """
    gateway = getattr(request.app.state, "market_data_gateway", None)
    if gateway is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="market data is not configured",
        )
    return gateway  # type: ignore[no-any-return]


def get_instrument_details_use_case(
    gateway: Annotated[TwelveDataGateway, Depends(get_market_data_gateway)],
) -> GetInstrumentDetails:
    return GetInstrumentDetails(gateway)


def get_instrument_price_history_use_case(
    gateway: Annotated[TwelveDataGateway, Depends(get_market_data_gateway)],
) -> GetInstrumentPriceHistory:
    return GetInstrumentPriceHistory(gateway)


def get_search_instruments_use_case(
    gateway: Annotated[TwelveDataGateway, Depends(get_market_data_gateway)],
) -> SearchInstruments:
    return SearchInstruments(gateway)


def get_news_gateway(request: Request) -> FinnhubNewsGateway:
    """Same optional-feature pattern as `get_market_data_gateway`, a
    separate provider/secret (`TRADING_AI_NEWS_API_KEY` -> Finnhub)."""
    gateway = getattr(request.app.state, "news_gateway", None)
    if gateway is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="news is not configured",
        )
    return gateway  # type: ignore[no-any-return]


def get_instrument_news_use_case(
    gateway: Annotated[FinnhubNewsGateway, Depends(get_news_gateway)],
) -> GetInstrumentNews:
    return GetInstrumentNews(gateway)


def get_optional_news_gateway(request: Request) -> FinnhubNewsGateway | None:
    """Unlike `get_news_gateway`, never raises.

    The AI-analysis endpoint degrades gracefully when news isn't
    configured at all (task scope §9) — same treatment as a
    configured-but-failing news call, not a hard failure of the whole
    analysis over one optional data source.
    """
    gateway = getattr(request.app.state, "news_gateway", None)
    return gateway


def get_ai_gateway(request: Request) -> XAIGateway:
    """Same optional-feature pattern as `get_market_data_gateway`, a
    third separate provider/secret (`TRADING_AI_LLM_API_KEY` -> xAI)."""
    gateway = getattr(request.app.state, "ai_gateway", None)
    if gateway is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI analysis is not configured",
        )
    return gateway  # type: ignore[no-any-return]


def get_generate_instrument_analysis_use_case(
    ai_gateway: Annotated[XAIGateway, Depends(get_ai_gateway)],
    market_gateway: Annotated[TwelveDataGateway, Depends(get_market_data_gateway)],
    optional_news_gateway: Annotated[
        FinnhubNewsGateway | None, Depends(get_optional_news_gateway)
    ],
) -> GenerateInstrumentAnalysis:
    news_use_case = (
        GetInstrumentNews(optional_news_gateway) if optional_news_gateway is not None else None
    )
    return GenerateInstrumentAnalysis(
        details_use_case=GetInstrumentDetails(market_gateway),
        history_use_case=GetInstrumentPriceHistory(market_gateway),
        news_use_case=news_use_case,
        ai_gateway=ai_gateway,
    )


@router.get("/instruments/search", response_model=InstrumentSearchResponse)
async def search_instruments(
    q: str,
    use_case: Annotated[SearchInstruments, Depends(get_search_instruments_use_case)],
) -> InstrumentSearchResponse:
    """Registered *before* `GET /instruments/{ticker}` below — Starlette
    matches routes in registration order, and `/instruments/{ticker}`
    would otherwise swallow `/instruments/search` requests as
    `ticker="search"` (task scope §6: a clean, unambiguous REST
    contract)."""
    results = await use_case.execute(q)
    return InstrumentSearchResponse(
        query=q.strip(),
        items=[
            InstrumentSearchResultResponse(
                ticker=result.ticker,
                name=result.name,
                exchange=result.exchange,
                instrument_type=result.instrument_type,
                currency=result.currency,
            )
            for result in results
        ],
    )


@router.get("/instruments/{ticker}", response_model=InstrumentDetailsResponse)
async def get_instrument_details(
    ticker: str,
    use_case: Annotated[GetInstrumentDetails, Depends(get_instrument_details_use_case)],
) -> InstrumentDetailsResponse:
    snapshot = await use_case.execute(ticker)
    return InstrumentDetailsResponse(
        ticker=snapshot.ticker,
        price=snapshot.price,
        change=snapshot.change,
        change_percent=snapshot.change_percent,
        open=snapshot.open,
        high=snapshot.high,
        low=snapshot.low,
        previous_close=snapshot.previous_close,
        volume=snapshot.volume,
        as_of=snapshot.as_of,
        source=snapshot.source,
    )


@router.get("/instruments/{ticker}/history", response_model=InstrumentHistoryResponse)
async def get_instrument_price_history(
    ticker: str,
    period: str,
    use_case: Annotated[
        GetInstrumentPriceHistory, Depends(get_instrument_price_history_use_case)
    ],
) -> InstrumentHistoryResponse:
    history = await use_case.execute(ticker, period)
    return InstrumentHistoryResponse(
        ticker=history.ticker,
        period=history.period.value,
        source=history.source,
        points=[
            InstrumentHistoryPointResponse(timestamp=point.timestamp, close=point.close)
            for point in history.points
        ],
    )


@router.get("/instruments/{ticker}/news", response_model=InstrumentNewsResponse)
async def get_instrument_news(
    ticker: str,
    use_case: Annotated[GetInstrumentNews, Depends(get_instrument_news_use_case)],
) -> InstrumentNewsResponse:
    news = await use_case.execute(ticker)
    return InstrumentNewsResponse(
        ticker=news.ticker,
        source=news.source,
        items=[
            InstrumentNewsItemResponse(
                id=item.id,
                headline=item.headline,
                source=item.source,
                published_at=item.published_at,
                url=item.url,
                summary=item.summary,
            )
            for item in news.items
        ],
    )


@router.post("/instruments/{ticker}/analysis", response_model=InstrumentAnalysisResponse)
async def generate_instrument_analysis(
    ticker: str,
    use_case: Annotated[
        GenerateInstrumentAnalysis, Depends(get_generate_instrument_analysis_use_case)
    ],
) -> InstrumentAnalysisResponse:
    """No request body is accepted — the ticker comes from the path only
    (task scope §6: the endpoint never accepts a free-form prompt).
    POST, not GET, since this triggers a paid/computational LLM
    generation call rather than a cached-feeling read (task scope §10)."""
    analysis = await use_case.execute(ticker)
    return InstrumentAnalysisResponse(
        ticker=analysis.ticker,
        generated_at=analysis.generated_at,
        summary=analysis.summary,
        price_context=analysis.price_context,
        news_context=analysis.news_context,
        risks=list(analysis.risks),
        disclaimer=analysis.disclaimer,
        source=analysis.provider,
    )


def register_ai_analysis_exception_handlers(app: FastAPI) -> None:
    """Map AI-analysis errors to safe, controlled HTTP responses.

    `InvalidTickerError` (raised by `normalize_ticker` inside the use
    case) is already handled globally by
    `register_watchlist_exception_handlers` (422). Same MRO-based
    dispatch pattern as `register_instruments_exception_handlers`: the
    `AIAnalysisError` base-class handler is the fallback for
    `AIProviderUnavailableError`/`AIInvalidOutputError`, which don't
    need a more specific status code than 503.
    """

    @app.exception_handler(AIInsufficientDataError)
    async def _handle_insufficient_data(
        _request: Request, _exc: AIInsufficientDataError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "insufficient data to generate an analysis"},
        )

    @app.exception_handler(AIRateLimitedError)
    async def _handle_ai_rate_limited(_request: Request, _exc: AIRateLimitedError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "AI provider is rate limited"},
        )

    @app.exception_handler(AITimeoutError)
    async def _handle_ai_timeout(_request: Request, _exc: AITimeoutError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content={"detail": "AI provider timed out"},
        )

    @app.exception_handler(AIAnalysisError)
    async def _handle_ai_analysis_error(_request: Request, _exc: AIAnalysisError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "AI analysis is unavailable"},
        )


def register_instruments_exception_handlers(app: FastAPI) -> None:
    """Map market-data errors to safe, controlled HTTP responses.

    `InvalidTickerError` (raised by `normalize_ticker` inside the use
    case) is already handled globally by
    `register_watchlist_exception_handlers` (422) — not duplicated
    here, since FastAPI exception handlers apply app-wide, not per
    router.

    Starlette dispatches on `type(exc).__mro__`, most specific first:
    `TickerUnsupportedError`/`MarketDataRateLimitedError`/
    `MarketDataTimeoutError` get their own status codes below, and the
    `MarketDataError` base-class handler is the fallback for the two
    subclasses that don't need a more specific one
    (`MarketDataUnavailableError`, `MarketDataMalformedResponseError`)
    — both are safely a 503, never the raw provider/exception detail.
    """

    @app.exception_handler(InvalidPeriodError)
    async def _handle_invalid_period(_request: Request, exc: InvalidPeriodError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.reason},
        )

    @app.exception_handler(InvalidSearchQueryError)
    async def _handle_invalid_search_query(
        _request: Request, exc: InvalidSearchQueryError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.reason},
        )

    @app.exception_handler(TickerUnsupportedError)
    async def _handle_ticker_unsupported(
        _request: Request, _exc: TickerUnsupportedError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "instrument not found"},
        )

    @app.exception_handler(MarketDataRateLimitedError)
    async def _handle_rate_limited(
        _request: Request, _exc: MarketDataRateLimitedError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "market data provider is rate limited"},
        )

    @app.exception_handler(MarketDataTimeoutError)
    async def _handle_timeout(_request: Request, _exc: MarketDataTimeoutError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content={"detail": "market data provider timed out"},
        )

    @app.exception_handler(MarketDataError)
    async def _handle_market_data_error(_request: Request, _exc: MarketDataError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "market data provider is unavailable"},
        )
