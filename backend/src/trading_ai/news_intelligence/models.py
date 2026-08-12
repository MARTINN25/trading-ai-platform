"""SQLAlchemy persistence model for `news_intelligence_items`.

Append-only, same rule as `insights.models.InsightModel`: no `updated_at`,
no UPDATE codepath in this package's repository — a row is only ever
inserted or read. The unique constraint on `(ticker, news_provider,
provider_news_id)` is what makes this table double as the reuse cache
(task scope §10): a row already existing for that triple means this
exact article, for this exact ticker, has already been processed once —
`GetNewsIntelligence` (`use_cases.py`) checks for existing rows before
calling the LLM at all, never on every page refresh.

No raw provider payload is stored — only the same small set of fields
`InstrumentNewsItem` already carries (headline/source/published_at/url)
plus the enrichment result. This is a deliberately minimal,
news-intelligence-owned schema (task scope §10: "не добавлять large raw
provider payload storage").
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Identity, Index, String, Text, UniqueConstraint, func
from sqlalchemy import BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from trading_ai.infrastructure.database.base import Base
from trading_ai.watchlist.domain import MAX_TICKER_LENGTH

_NEWS_PROVIDER_MAX_LENGTH = 50
_PROVIDER_NEWS_ID_MAX_LENGTH = 100
_SOURCE_MAX_LENGTH = 200
_URL_MAX_LENGTH = 2000
_RELEVANCE_MAX_LENGTH = 10
_RELATIONSHIP_MAX_LENGTH = 10
_LLM_PROVIDER_MAX_LENGTH = 50
_LLM_MODEL_MAX_LENGTH = 100
_LLM_VERSION_MAX_LENGTH = 50


class NewsIntelligenceItemModel(Base):
    __tablename__ = "news_intelligence_items"
    __table_args__ = (
        UniqueConstraint(
            "ticker",
            "news_provider",
            "provider_news_id",
            name="uq_news_intelligence_ticker_provider_item",
        ),
        Index("ix_news_intelligence_ticker_published_at", "ticker", "published_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    ticker: Mapped[str] = mapped_column(String(MAX_TICKER_LENGTH), nullable=False)
    news_provider: Mapped[str] = mapped_column(String(_NEWS_PROVIDER_MAX_LENGTH), nullable=False)
    provider_news_id: Mapped[str] = mapped_column(
        String(_PROVIDER_NEWS_ID_MAX_LENGTH), nullable=False
    )
    headline_original: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(_SOURCE_MAX_LENGTH), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    url: Mapped[str] = mapped_column(String(_URL_MAX_LENGTH), nullable=False)

    enriched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    summary_ru: Mapped[str | None] = mapped_column(Text)
    why_it_matters: Mapped[str | None] = mapped_column(Text)
    relevance: Mapped[str | None] = mapped_column(String(_RELEVANCE_MAX_LENGTH))
    relationship: Mapped[str | None] = mapped_column(String(_RELATIONSHIP_MAX_LENGTH))
    impact_hypothesis: Mapped[str | None] = mapped_column(Text)

    llm_provider: Mapped[str | None] = mapped_column(String(_LLM_PROVIDER_MAX_LENGTH))
    llm_model: Mapped[str | None] = mapped_column(String(_LLM_MODEL_MAX_LENGTH))
    llm_prompt_version: Mapped[str | None] = mapped_column(String(_LLM_VERSION_MAX_LENGTH))
    llm_schema_version: Mapped[str | None] = mapped_column(String(_LLM_VERSION_MAX_LENGTH))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
