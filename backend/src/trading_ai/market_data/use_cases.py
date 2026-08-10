"""Market-data application use cases.

Unlike `watchlist.use_cases`, `GetInstrumentDetails` depends only on
the provider-neutral market-data gateway (`_InstrumentGatewayLike`) —
it never touches a repository or opens a database session, because
instrument details is a read-only, market-data-only lookup, not a
combined watchlist+market-data operation (task scope).

Ticker normalization is reused from `trading_ai.watchlist.domain`
rather than duplicated: it is a pure, DB-free function (trim/
uppercase/charset validation), so importing it here does not pull in
any watchlist persistence dependency.
"""

from __future__ import annotations

from typing import Protocol

from trading_ai.market_data.types import (
    InstrumentHistoryPeriod,
    InstrumentNews,
    InstrumentSnapshot,
    PriceHistory,
    normalize_period,
)
from trading_ai.watchlist.domain import normalize_ticker


class _InstrumentGatewayLike(Protocol):
    async def get_instrument_snapshot(self, ticker: str) -> InstrumentSnapshot: ...


class GetInstrumentDetails:
    def __init__(self, gateway: _InstrumentGatewayLike) -> None:
        self._gateway = gateway

    async def execute(self, raw_ticker: str) -> InstrumentSnapshot:
        ticker = normalize_ticker(raw_ticker)
        return await self._gateway.get_instrument_snapshot(ticker)


class _InstrumentHistoryGatewayLike(Protocol):
    async def get_price_history(
        self, ticker: str, period: InstrumentHistoryPeriod
    ) -> PriceHistory: ...


class GetInstrumentPriceHistory:
    """Read-only chart-history lookup — same shape as `GetInstrumentDetails`:
    depends only on the gateway, never opens a database session, never
    persists anything (task scope §4)."""

    def __init__(self, gateway: _InstrumentHistoryGatewayLike) -> None:
        self._gateway = gateway

    async def execute(self, raw_ticker: str, raw_period: str) -> PriceHistory:
        ticker = normalize_ticker(raw_ticker)
        period = normalize_period(raw_period)
        return await self._gateway.get_price_history(ticker, period)


class _InstrumentNewsGatewayLike(Protocol):
    async def get_instrument_news(self, ticker: str) -> InstrumentNews: ...


class GetInstrumentNews:
    """Read-only news lookup — same shape as `GetInstrumentDetails`:
    depends only on the gateway, never opens a database session, never
    persists anything (task scope §4)."""

    def __init__(self, gateway: _InstrumentNewsGatewayLike) -> None:
        self._gateway = gateway

    async def execute(self, raw_ticker: str) -> InstrumentNews:
        ticker = normalize_ticker(raw_ticker)
        return await self._gateway.get_instrument_news(ticker)
