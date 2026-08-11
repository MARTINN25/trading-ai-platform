"""Insight persistence application use cases.

`GenerateInstrumentAnalysis` (`ai/use_cases.py`) is unchanged in
responsibility — it only generates, it still never opens a database
session or persists anything (task scope §11: "не превращать
GenerateInstrumentAnalysis в ORM use case напрямую"). Saving is a
deliberately separate use case here, matching MODULE_BOUNDARIES.md
§11's rule that `insights` "не выполняет сбор данных" — it only
receives an already-formed result and stores it.
"""

from __future__ import annotations

from typing import Protocol

from trading_ai.ai.pending_cache import PendingAnalysisCache
from trading_ai.ai.types import InstrumentAnalysis
from trading_ai.insights.domain import (
    InsightNotFoundError,
    NewInsight,
    PendingAnalysisNotFoundError,
    SavedInsight,
)
from trading_ai.watchlist.domain import normalize_ticker


class _InsightRepositoryLike(Protocol):
    async def add(self, insight: NewInsight) -> SavedInsight: ...

    async def list_recent_for_ticker(self, ticker: str) -> list[SavedInsight]: ...

    async def get_by_id(self, insight_id: int) -> SavedInsight | None: ...


def _to_new_insight(analysis: InstrumentAnalysis) -> NewInsight:
    return NewInsight(
        ticker=analysis.ticker,
        generated_at=analysis.generated_at,
        summary=analysis.summary,
        price_context=analysis.price_context,
        news_context=analysis.news_context,
        key_facts=analysis.key_facts,
        insight_hypothesis=analysis.insight_hypothesis,
        confidence=analysis.confidence,
        confidence_reason=analysis.confidence_reason,
        considerations=analysis.considerations,
        risks=analysis.risks,
        key_drivers=analysis.key_drivers,
        data_freshness=analysis.data_freshness,
        source_data_as_of=analysis.source_data_as_of,
        disclaimer=analysis.disclaimer,
        provider=analysis.provider,
        model=analysis.model,
        prompt_version=analysis.prompt_version,
        schema_version=analysis.schema_version,
    )


class SaveInsight:
    """Persists the *server-held* pending analysis for `(ticker,
    analysis_token)` — never any analysis content supplied directly by
    the caller (task scope §12)."""

    def __init__(
        self, repository: _InsightRepositoryLike, pending_cache: PendingAnalysisCache
    ) -> None:
        self._repository = repository
        self._pending_cache = pending_cache

    async def execute(self, raw_ticker: str, analysis_token: str) -> SavedInsight:
        ticker = normalize_ticker(raw_ticker)
        analysis = self._pending_cache.pop(ticker, analysis_token)
        if analysis is None:
            raise PendingAnalysisNotFoundError(ticker)
        return await self._repository.add(_to_new_insight(analysis))


class ListInstrumentInsights:
    def __init__(self, repository: _InsightRepositoryLike) -> None:
        self._repository = repository

    async def execute(self, raw_ticker: str) -> list[SavedInsight]:
        ticker = normalize_ticker(raw_ticker)
        return await self._repository.list_recent_for_ticker(ticker)


class GetInsightDetail:
    def __init__(self, repository: _InsightRepositoryLike) -> None:
        self._repository = repository

    async def execute(self, insight_id: int) -> SavedInsight:
        insight = await self._repository.get_by_id(insight_id)
        if insight is None:
            raise InsightNotFoundError(insight_id)
        return insight
