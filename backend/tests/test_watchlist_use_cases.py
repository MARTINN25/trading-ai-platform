from __future__ import annotations

from datetime import datetime, timezone

import pytest

from trading_ai.watchlist.domain import (
    DuplicateTickerError,
    InvalidTickerError,
    WatchlistItem,
)
from trading_ai.watchlist.use_cases import AddWatchlistItem, ListWatchlistItems


class FakeWatchlistRepository:
    """In-memory test double — not a generic repository abstraction.

    Mirrors `WatchlistRepository`'s two methods only, enough to test
    the use cases without a database.
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
