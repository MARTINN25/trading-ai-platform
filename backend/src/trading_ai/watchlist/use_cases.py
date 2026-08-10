"""Watchlist application use cases.

The only layer that knows both the domain rules (ticker normalization)
and the repository. The API route calls these, never the repository or
the database directly (ADR-0002, §17).

Use cases depend on `_WatchlistRepositoryLike`, a narrow structural
`Protocol` matching `WatchlistRepository`'s two methods — not a
generic repository abstraction, just enough typing to let unit tests
pass an in-memory fake without subclassing the real (session-backed)
repository. `ListWatchlistItemsWithQuotes` depends on
`_MarketDataGatewayLike` the same way — watchlist code depends on the
market-data *contract* (`market_data.types`), never on the concrete
Twelve Data gateway/httpx.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from trading_ai.market_data.types import (
    MarketDataError,
    MarketDataRateLimitedError,
    MarketDataTimeoutError,
    MarketQuote,
    TickerUnsupportedError,
)
from trading_ai.watchlist.domain import (
    WatchlistItem,
    WatchlistItemNotFoundError,
    normalize_ticker,
)


class _WatchlistRepositoryLike(Protocol):
    async def add(self, ticker: str) -> WatchlistItem: ...

    async def remove(self, item_id: int) -> bool: ...

    async def list_all(self) -> list[WatchlistItem]: ...


class _MarketDataGatewayLike(Protocol):
    async def get_quote(self, ticker: str) -> MarketQuote: ...


class AddWatchlistItem:
    def __init__(self, repository: _WatchlistRepositoryLike) -> None:
        self._repository = repository

    async def execute(self, raw_ticker: str) -> WatchlistItem:
        ticker = normalize_ticker(raw_ticker)
        return await self._repository.add(ticker)


class RemoveWatchlistItem:
    def __init__(self, repository: _WatchlistRepositoryLike) -> None:
        self._repository = repository

    async def execute(self, item_id: int) -> None:
        deleted = await self._repository.remove(item_id)
        if not deleted:
            raise WatchlistItemNotFoundError(item_id)


class ListWatchlistItems:
    def __init__(self, repository: _WatchlistRepositoryLike) -> None:
        self._repository = repository

    async def execute(self) -> list[WatchlistItem]:
        return await self._repository.list_all()


@dataclass(frozen=True, slots=True)
class WatchlistItemQuoteResult:
    """One watchlist item plus its quote — or a safe error category.

    Exactly one of `quote`/`error` is set. Never both `None` (a
    successful call always returns a quote; a failed one always sets a
    category) and never both set (a failure never carries stale/partial
    quote data — no silently-stale numbers, per task scope).
    """

    item: WatchlistItem
    quote: MarketQuote | None
    error: str | None


def _error_category(exc: MarketDataError) -> str:
    """Map a market-data exception to a short, safe, user-facing category.

    Never includes `str(exc)` — that could (in principle, for a
    misbehaving provider) contain response fragments; only the fixed
    category string crosses this boundary.
    """
    if isinstance(exc, MarketDataTimeoutError):
        return "timeout"
    if isinstance(exc, MarketDataRateLimitedError):
        return "rate_limited"
    if isinstance(exc, TickerUnsupportedError):
        return "unsupported"
    return "unavailable"


class ListWatchlistItemsWithQuotes:
    """Watchlist rows enriched with a best-effort quote per item.

    One failing ticker/provider call never fails the whole list — each
    item's quote is fetched independently and a failure becomes a safe
    `error` category on that single result (task scope, §3–4).
    Sequential, not concurrent: Twelve Data's basic quote endpoint has
    no documented free-tier batch/multi-symbol call (researched before
    implementation), so this is the simplest correct fan-out limit
    (effectively concurrency 1) rather than firing N unbounded
    concurrent requests.
    """

    def __init__(
        self,
        repository: _WatchlistRepositoryLike,
        gateway: _MarketDataGatewayLike,
    ) -> None:
        self._repository = repository
        self._gateway = gateway

    async def execute(self) -> list[WatchlistItemQuoteResult]:
        items = await self._repository.list_all()
        results: list[WatchlistItemQuoteResult] = []
        for item in items:
            try:
                quote = await self._gateway.get_quote(item.ticker)
            except MarketDataError as exc:
                results.append(
                    WatchlistItemQuoteResult(
                        item=item, quote=None, error=_error_category(exc)
                    )
                )
            else:
                results.append(WatchlistItemQuoteResult(item=item, quote=quote, error=None))
        return results
