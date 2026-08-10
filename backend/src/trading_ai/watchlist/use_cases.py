"""Watchlist application use cases.

The only layer that knows both the domain rules (ticker normalization)
and the repository. The API route calls these, never the repository or
the database directly (ADR-0002, §17).

Use cases depend on `_WatchlistRepositoryLike`, a narrow structural
`Protocol` matching `WatchlistRepository`'s two methods — not a
generic repository abstraction, just enough typing to let unit tests
pass an in-memory fake without subclassing the real (session-backed)
repository.
"""

from __future__ import annotations

from typing import Protocol

from trading_ai.watchlist.domain import (
    WatchlistItem,
    WatchlistItemNotFoundError,
    normalize_ticker,
)


class _WatchlistRepositoryLike(Protocol):
    async def add(self, ticker: str) -> WatchlistItem: ...

    async def remove(self, item_id: int) -> bool: ...

    async def list_all(self) -> list[WatchlistItem]: ...


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
