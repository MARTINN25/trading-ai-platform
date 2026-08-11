"""SQLAlchemy persistence model for `journal_entries`.

Kept separate from `trading_ai.journal.domain.JournalEntry`, same split
as `insights.models`/`insights.domain` and
`evaluations.models`/`evaluations.domain`.

Unlike `insights`/`insight_evaluations`, this table *does* support
`UPDATE` (Product Owner: editable, no delete) — `updated_at` is set by
the repository on every edit, `created_at` never changes.

Plain relational columns, not JSONB — every field here is a small,
fixed, individually-queryable fact (ticker, direction, status), not a
variable-length list, so there is no reason to reach for JSONB the way
`insights.key_facts`/etc. did (ADR-0004 §22: JSONB only for genuinely
variable attributes).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from trading_ai.infrastructure.database.base import Base

# Imported for its side effect of registering `insights` on
# `Base.metadata` before this module's FK to `insights.id` is resolved
# (SQLAlchemy resolves string-form FK targets by table name at
# flush/mapper-configuration time, not at import time of this module
# alone) — required so `journal.models` never depends on some *other*
# module having already imported `insights.models` first. Not used
# directly here.
from trading_ai.insights import models as _insights_models  # noqa: F401
from trading_ai.watchlist.domain import MAX_TICKER_LENGTH

_DIRECTION_MAX_LENGTH = 10
_RESULT_STATUS_MAX_LENGTH = 20


class JournalEntryModel(Base):
    __tablename__ = "journal_entries"
    __table_args__ = (Index("ix_journal_entries_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    ticker: Mapped[str] = mapped_column(String(MAX_TICKER_LENGTH), nullable=False)
    direction: Mapped[str] = mapped_column(String(_DIRECTION_MAX_LENGTH), nullable=False)
    result_status: Mapped[str] = mapped_column(String(_RESULT_STATUS_MAX_LENGTH), nullable=False)
    result_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    insight_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("insights.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
