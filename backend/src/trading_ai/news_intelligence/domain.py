"""News Intelligence persistence domain model — mirrors `insights.domain`'s split
between a plain value object and the SQLAlchemy model (`models.py`).

`PersistedNewsIntelligenceItem` is immutable and append-only, same rule
as `SavedInsight` (ADR-0004 §20): once an item has been enriched (or
recorded as "seen, LLM failed for it") for a given `(ticker, news_provider,
provider_news_id)`, that row is never rewritten — a later request either
reuses it as-is or, if it was never successfully enriched, may attempt
enrichment again (see `use_cases.py`'s reuse policy).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from trading_ai.ai.types import NewsRelationship, NewsRelevance


@dataclass(frozen=True, slots=True)
class NewNewsIntelligenceRow:
    """Everything the repository needs to insert one row."""

    ticker: str
    news_provider: str
    provider_news_id: str
    headline_original: str
    source: str
    published_at: datetime
    url: str
    enriched: bool
    summary_ru: str | None
    why_it_matters: str | None
    relevance: NewsRelevance | None
    relationship: NewsRelationship | None
    impact_hypothesis: str | None
    llm_provider: str | None
    llm_model: str | None
    llm_prompt_version: str | None
    llm_schema_version: str | None


@dataclass(frozen=True, slots=True)
class PersistedNewsIntelligenceItem:
    """One immutable, persisted row — the repository-facing shape."""

    id: int
    ticker: str
    news_provider: str
    provider_news_id: str
    headline_original: str
    source: str
    published_at: datetime
    url: str
    enriched: bool
    summary_ru: str | None
    why_it_matters: str | None
    relevance: NewsRelevance | None
    relationship: NewsRelationship | None
    impact_hypothesis: str | None
    llm_provider: str | None
    llm_model: str | None
    llm_prompt_version: str | None
    llm_schema_version: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CuratedNewsItem:
    """The application/API-facing shape returned by `GetNewsIntelligence`
    (`use_cases.py`) — deliberately narrower than `PersistedNewsIntelligenceItem`:
    LLM provenance (`llm_provider`/`llm_model`/...) stays internal to the
    persistence layer, not surfaced to the API response (task scope §4:
    "provenance/version metadata where appropriate" — appropriate here
    means enough to explain the item, not a full internal trace)."""

    id: str
    ticker: str
    headline: str
    source: str
    published_at: datetime
    url: str
    summary: str | None
    enriched: bool
    summary_ru: str | None
    why_it_matters: str | None
    relevance: NewsRelevance | None
    relationship: NewsRelationship | None
    impact_hypothesis: str | None


@dataclass(frozen=True, slots=True)
class CuratedNews:
    """A requested ticker's curated news-intelligence feed — bounded,
    ranked, NOISE-excluded (see `use_cases.py`'s curation policy)."""

    ticker: str
    source: str
    items: tuple[CuratedNewsItem, ...]
