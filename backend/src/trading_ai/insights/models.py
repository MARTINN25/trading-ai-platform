"""SQLAlchemy persistence model for `insights`.

Kept separate from `trading_ai.insights.domain.SavedInsight`, same
split as `watchlist.models`/`watchlist.domain` (ADR-0002 §18.2). No
`updated_at`, no UPDATE codepath anywhere in this package — a row is
only ever inserted or read, never modified in place (ADR-0004 §20,
task scope §7: immutability is enforced by *not writing* an update
operation, not by a DB trigger — the same level of enforcement ADR-0004
itself allows: "обеспечивается на уровне application layer").

`key_facts`/`considerations`/`risks`/`key_drivers` are JSONB, not
separate child tables — each is a small, variable-length list of
strings/short objects owned entirely by one insight row and never
queried independently of it; normalizing them into 4 extra tables
would be over-normalization for data that's never joined or filtered
on its own (task scope §8: "не нормализовать в 8 таблиц без
необходимости"). `jsonb` (not `json`) per ADR-0004 §22's own
recommendation for variable attributes.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Identity, Index, String, Text, func
from sqlalchemy import BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from trading_ai.infrastructure.database.base import Base
from trading_ai.watchlist.domain import MAX_TICKER_LENGTH

_PROVIDER_MAX_LENGTH = 50
_MODEL_MAX_LENGTH = 100
_VERSION_MAX_LENGTH = 50
_CONFIDENCE_MAX_LENGTH = 10


class InsightModel(Base):
    __tablename__ = "insights"
    __table_args__ = (
        Index("ix_insights_ticker_created_at", "ticker", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    ticker: Mapped[str] = mapped_column(String(MAX_TICKER_LENGTH), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    summary: Mapped[str] = mapped_column(Text, nullable=False)
    price_context: Mapped[str] = mapped_column(Text, nullable=False)
    news_context: Mapped[str] = mapped_column(Text, nullable=False)
    key_facts: Mapped[list[dict[str, str]]] = mapped_column(JSONB, nullable=False)
    insight_hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(String(_CONFIDENCE_MAX_LENGTH), nullable=False)
    confidence_reason: Mapped[str] = mapped_column(Text, nullable=False)
    considerations: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    risks: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    key_drivers: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    data_freshness: Mapped[str] = mapped_column(Text, nullable=False)
    source_data_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disclaimer: Mapped[str] = mapped_column(Text, nullable=False)

    provider: Mapped[str] = mapped_column(String(_PROVIDER_MAX_LENGTH), nullable=False)
    model: Mapped[str] = mapped_column(String(_MODEL_MAX_LENGTH), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(_VERSION_MAX_LENGTH), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(_VERSION_MAX_LENGTH), nullable=False)
