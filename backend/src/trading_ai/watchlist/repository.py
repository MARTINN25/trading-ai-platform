"""Concrete watchlist repository — no generic repository abstraction.

Owns no transaction boundary: whoever obtained the `AsyncSession`
(`trading_ai.infrastructure.database.session.session_scope`) decides
when to commit or roll back — this repository never calls `commit()`.

`add()` explicitly flushes so a duplicate ticker is caught here, via
the database's own UNIQUE constraint, rather than a preceding `SELECT`
(which would not be safe under a concurrent insert of the same
ticker, ADR-0004 §25/§466).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from trading_ai.watchlist.domain import DuplicateTickerError, WatchlistItem
from trading_ai.watchlist.models import WatchlistItemModel


def _to_domain(model: WatchlistItemModel) -> WatchlistItem:
    return WatchlistItem(id=model.id, ticker=model.ticker, created_at=model.created_at)


class WatchlistRepository:
    """Concrete repository for `watchlist_items` — no generic base class."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, ticker: str) -> WatchlistItem:
        """Insert an already-normalized ticker.

        Raises `DuplicateTickerError` if the ticker already exists,
        translated from the database's UNIQUE constraint violation.
        """
        model = WatchlistItemModel(ticker=ticker)
        self._session.add(model)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise DuplicateTickerError(ticker) from exc
        return _to_domain(model)

    async def list_all(self) -> list[WatchlistItem]:
        """List all items, oldest first.

        Ordered by `created_at` then `id` — `created_at` alone is not
        unique (server-side `now()` can repeat within the same
        transaction/statement), so `id` breaks ties deterministically
        instead of leaving the order to whatever the database happens
        to return.
        """
        result = await self._session.execute(
            select(WatchlistItemModel).order_by(
                WatchlistItemModel.created_at, WatchlistItemModel.id
            )
        )
        return [_to_domain(model) for model in result.scalars()]
