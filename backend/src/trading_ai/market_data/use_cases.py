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

from trading_ai.market_data.types import InstrumentSnapshot
from trading_ai.watchlist.domain import normalize_ticker


class _InstrumentGatewayLike(Protocol):
    async def get_instrument_snapshot(self, ticker: str) -> InstrumentSnapshot: ...


class GetInstrumentDetails:
    def __init__(self, gateway: _InstrumentGatewayLike) -> None:
        self._gateway = gateway

    async def execute(self, raw_ticker: str) -> InstrumentSnapshot:
        ticker = normalize_ticker(raw_ticker)
        return await self._gateway.get_instrument_snapshot(ticker)
