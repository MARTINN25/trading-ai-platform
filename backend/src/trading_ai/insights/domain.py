"""Insight persistence domain model (MODULE_BOUNDARIES.md §11 "insights").

Deliberately not the SQLAlchemy model (`trading_ai.insights.models`):
`SavedInsight` is a plain, immutable value object with no ORM
dependency, mirroring `watchlist.domain.WatchlistItem`'s split. This
module owns no generation logic and no repository access — it only
defines the shape of a persisted insight and the errors around it
(MODULE_BOUNDARIES.md §11: "insights не выполняет сбор данных").

`SavedInsight` is immutable by construction (frozen dataclass) and this
module defines no update operation — ADR-0004 §20: "insight record не
переписывается задним числом". A new generation/save always produces a
new row; there is no edit-insight feature in this slice (task scope §7, §29).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from trading_ai.ai.types import ConfidenceLevel, KeyFact


class InsightError(Exception):
    """Base class for insight persistence domain/application errors."""


class PendingAnalysisNotFoundError(InsightError):
    """Raised when a save is attempted with an unknown, expired, or
    ticker-mismatched `analysis_token` — never a signal to trust
    arbitrary client-supplied analysis content instead (task scope §12)."""

    def __init__(self, ticker: str) -> None:
        super().__init__(f"no pending analysis to save for {ticker}")
        self.ticker = ticker


class InsightNotFoundError(InsightError):
    """Raised when a requested insight id does not exist."""

    def __init__(self, insight_id: int) -> None:
        super().__init__(f"insight not found: {insight_id}")
        self.insight_id = insight_id


@dataclass(frozen=True, slots=True)
class NewInsight:
    """Everything the repository needs to insert one row — assembled by
    `SaveInsight` (`use_cases.py`) exclusively from a server-held
    `InstrumentAnalysis` (never from client-supplied request fields,
    task scope §12)."""

    ticker: str
    generated_at: datetime
    summary: str
    price_context: str
    news_context: str
    key_facts: tuple[KeyFact, ...]
    insight_hypothesis: str
    confidence: ConfidenceLevel
    confidence_reason: str
    considerations: tuple[str, ...]
    risks: tuple[str, ...]
    key_drivers: tuple[str, ...]
    data_freshness: str
    source_data_as_of: datetime | None
    disclaimer: str
    provider: str
    model: str
    prompt_version: str
    schema_version: str


@dataclass(frozen=True, slots=True)
class SavedInsight:
    """One immutable, persisted insight row — the application/API-facing shape."""

    id: int
    ticker: str
    generated_at: datetime
    created_at: datetime
    summary: str
    price_context: str
    news_context: str
    key_facts: tuple[KeyFact, ...]
    insight_hypothesis: str
    confidence: ConfidenceLevel
    confidence_reason: str
    considerations: tuple[str, ...]
    risks: tuple[str, ...]
    key_drivers: tuple[str, ...]
    data_freshness: str
    source_data_as_of: datetime | None
    disclaimer: str
    provider: str
    model: str
    prompt_version: str
    schema_version: str


# Bounded history (task scope §14: "не делать infinite scroll... Максимум
# разумный bounded history count") — a fixed cap, not user-configurable
# pagination, matching this codebase's established pattern for other
# capped lists (e.g. news, search results).
MAX_HISTORY_ITEMS = 20
