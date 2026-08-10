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

from trading_ai.market_data.gateway import TwelveDataGateway
from trading_ai.market_data.types import (
    InvalidPeriodError,
    MarketDataError,
    MarketDataRateLimitedError,
    MarketDataTimeoutError,
    TickerUnsupportedError,
)
from trading_ai.market_data.use_cases import GetInstrumentDetails, GetInstrumentPriceHistory

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
