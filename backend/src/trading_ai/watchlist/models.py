"""SQLAlchemy persistence model for `watchlist_items`.

Kept separate from `trading_ai.watchlist.domain.WatchlistItem`: the ORM
model is an infrastructure detail, not what the API or application
layer exposes (ADR-0002, §18.2). No JSONB, no soft delete, no
`updated_at` — this table only ever gets a new row or a full row
deletion, never an in-place business update in this vertical slice.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Identity, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from trading_ai.infrastructure.database.base import Base
from trading_ai.watchlist.domain import MAX_TICKER_LENGTH


class WatchlistItemModel(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("ticker", name="uq_watchlist_items_ticker"),)

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), primary_key=True
    )
    ticker: Mapped[str] = mapped_column(String(MAX_TICKER_LENGTH), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
