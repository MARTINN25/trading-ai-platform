from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from trading_ai.market_data.types import MarketDataTimeoutError, MarketQuote
from trading_ai.watchlist.domain import (
    DuplicateTickerError,
    InvalidTickerError,
    WatchlistItem,
    WatchlistItemNotFoundError,
)
from trading_ai.watchlist.use_cases import (
    AddWatchlistItem,
    ListWatchlistItems,
    ListWatchlistItemsWithQuotes,
    RemoveWatchlistItem,
)


class FakeWatchlistRepository:
    """In-memory test double — not a generic repository abstraction.

    Mirrors `WatchlistRepository`'s methods only, enough to test the
    use cases without a database.
    """

    def __init__(self) -> None:
        self._items: list[WatchlistItem] = []
        self._next_id = 1

    async def add(self, ticker: str) -> WatchlistItem:
        if any(item.ticker == ticker for item in self._items):
            raise DuplicateTickerError(ticker)
        item = WatchlistItem(
            id=self._next_id, ticker=ticker, created_at=datetime.now(timezone.utc)
        )
        self._next_id += 1
        self._items.append(item)
        return item

    async def remove(self, item_id: int) -> bool:
        for index, item in enumerate(self._items):
            if item.id == item_id:
                del self._items[index]
                return True
        return False

    async def list_all(self) -> list[WatchlistItem]:
        return list(self._items)


@pytest.mark.anyio
async def test_add_watchlist_item_normalizes_and_stores() -> None:
    repository = FakeWatchlistRepository()
    use_case = AddWatchlistItem(repository)

    item = await use_case.execute("  aapl  ")

    assert item.ticker == "AAPL"
    assert isinstance(item, WatchlistItem)


@pytest.mark.anyio
async def test_add_watchlist_item_rejects_invalid_ticker_before_touching_repository() -> (
    None
):
    repository = FakeWatchlistRepository()
    use_case = AddWatchlistItem(repository)

    with pytest.raises(InvalidTickerError):
        await use_case.execute("   ")

    assert await repository.list_all() == []


@pytest.mark.anyio
async def test_add_watchlist_item_duplicate_raises_controlled_error() -> None:
    repository = FakeWatchlistRepository()
    use_case = AddWatchlistItem(repository)
    await use_case.execute("AAPL")

    with pytest.raises(DuplicateTickerError):
        await use_case.execute("aapl")


@pytest.mark.anyio
async def test_list_watchlist_items_returns_domain_objects_not_orm() -> None:
    repository = FakeWatchlistRepository()
    add_use_case = AddWatchlistItem(repository)
    list_use_case = ListWatchlistItems(repository)
    await add_use_case.execute("AAPL")
    await add_use_case.execute("MSFT")

    items = await list_use_case.execute()

    assert [item.ticker for item in items] == ["AAPL", "MSFT"]
    assert all(isinstance(item, WatchlistItem) for item in items)


@pytest.mark.anyio
async def test_remove_watchlist_item_deletes_existing_item() -> None:
    repository = FakeWatchlistRepository()
    add_use_case = AddWatchlistItem(repository)
    remove_use_case = RemoveWatchlistItem(repository)
    list_use_case = ListWatchlistItems(repository)
    item = await add_use_case.execute("AAPL")

    await remove_use_case.execute(item.id)

    assert await list_use_case.execute() == []


@pytest.mark.anyio
async def test_remove_watchlist_item_raises_controlled_not_found_error() -> None:
    repository = FakeWatchlistRepository()
    remove_use_case = RemoveWatchlistItem(repository)

    with pytest.raises(WatchlistItemNotFoundError):
        await remove_use_case.execute(999)


class FakeMarketDataGateway:
    """In-memory test double — not a generic provider framework.

    Configured per-ticker: either a canned `MarketQuote` or an
    exception to raise, so tests can simulate "one ticker fails, the
    rest succeed" without a real provider.
    """

    def __init__(
        self,
        quotes: dict[str, MarketQuote] | None = None,
        errors: dict[str, Exception] | None = None,
    ) -> None:
        self._quotes = quotes or {}
        self._errors = errors or {}

    async def get_quote(self, ticker: str) -> MarketQuote:
        if ticker in self._errors:
            raise self._errors[ticker]
        return self._quotes[ticker]


def _fake_quote(ticker: str) -> MarketQuote:
    return MarketQuote(
        ticker=ticker,
        price=Decimal("100.00"),
        change=Decimal("1.00"),
        change_percent=Decimal("1.00"),
        as_of=datetime.now(timezone.utc),
        source="fake",
    )


@pytest.mark.anyio
async def test_list_watchlist_items_with_quotes_returns_quote_for_each_item() -> None:
    repository = FakeWatchlistRepository()
    add_use_case = AddWatchlistItem(repository)
    await add_use_case.execute("AAPL")
    await add_use_case.execute("MSFT")
    gateway = FakeMarketDataGateway(
        quotes={"AAPL": _fake_quote("AAPL"), "MSFT": _fake_quote("MSFT")}
    )
    use_case = ListWatchlistItemsWithQuotes(repository, gateway)

    results = await use_case.execute()

    assert [r.item.ticker for r in results] == ["AAPL", "MSFT"]
    assert all(r.quote is not None and r.error is None for r in results)


@pytest.mark.anyio
async def test_list_watchlist_items_with_quotes_one_failure_does_not_fail_the_list() -> None:
    repository = FakeWatchlistRepository()
    add_use_case = AddWatchlistItem(repository)
    await add_use_case.execute("AAPL")
    await add_use_case.execute("MSFT")
    gateway = FakeMarketDataGateway(
        quotes={"MSFT": _fake_quote("MSFT")},
        errors={"AAPL": MarketDataTimeoutError("timed out")},
    )
    use_case = ListWatchlistItemsWithQuotes(repository, gateway)

    results = await use_case.execute()

    by_ticker = {r.item.ticker: r for r in results}
    assert by_ticker["AAPL"].quote is None
    assert by_ticker["AAPL"].error == "timeout"
    assert by_ticker["MSFT"].quote is not None
    assert by_ticker["MSFT"].error is None
