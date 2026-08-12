"""Concrete news-intelligence repository — no generic repository abstraction
(same pattern as `insights.repository.InsightRepository`).

Owns no transaction boundary: whoever obtained the `AsyncSession`
decides when to commit or roll back — this repository never calls
`commit()`.

Only `add`/`get_existing_for_ticker` exist — no update, no delete
(append-only, mirrors `insights.repository`). Concurrent duplicate
inserts for the same `(ticker, news_provider, provider_news_id)` are
not de-conflicted here beyond the DB's own unique constraint — an
accepted, documented limitation for this single-local-user MVP slice
(see the Phase 2A final report), not a silent correctness gap.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trading_ai.ai.types import NewsRelationship, NewsRelevance
from trading_ai.news_intelligence.domain import (
    NewNewsIntelligenceRow,
    PersistedNewsIntelligenceItem,
)
from trading_ai.news_intelligence.models import NewsIntelligenceItemModel


def _to_domain(model: NewsIntelligenceItemModel) -> PersistedNewsIntelligenceItem:
    return PersistedNewsIntelligenceItem(
        id=model.id,
        ticker=model.ticker,
        news_provider=model.news_provider,
        provider_news_id=model.provider_news_id,
        headline_original=model.headline_original,
        source=model.source,
        published_at=model.published_at,
        url=model.url,
        enriched=model.enriched,
        summary_ru=model.summary_ru,
        why_it_matters=model.why_it_matters,
        relevance=NewsRelevance(model.relevance) if model.relevance is not None else None,
        relationship=(
            NewsRelationship(model.relationship) if model.relationship is not None else None
        ),
        impact_hypothesis=model.impact_hypothesis,
        llm_provider=model.llm_provider,
        llm_model=model.llm_model,
        llm_prompt_version=model.llm_prompt_version,
        llm_schema_version=model.llm_schema_version,
        created_at=model.created_at,
    )


class NewsIntelligenceRepository:
    """Concrete repository for `news_intelligence_items` — no generic base class."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, row: NewNewsIntelligenceRow) -> PersistedNewsIntelligenceItem:
        model = NewsIntelligenceItemModel(
            ticker=row.ticker,
            news_provider=row.news_provider,
            provider_news_id=row.provider_news_id,
            headline_original=row.headline_original,
            source=row.source,
            published_at=row.published_at,
            url=row.url,
            enriched=row.enriched,
            summary_ru=row.summary_ru,
            why_it_matters=row.why_it_matters,
            relevance=row.relevance.value if row.relevance is not None else None,
            relationship=row.relationship.value if row.relationship is not None else None,
            impact_hypothesis=row.impact_hypothesis,
            llm_provider=row.llm_provider,
            llm_model=row.llm_model,
            llm_prompt_version=row.llm_prompt_version,
            llm_schema_version=row.llm_schema_version,
        )
        self._session.add(model)
        await self._session.flush()
        return _to_domain(model)

    async def get_existing_for_ticker(
        self, ticker: str, news_provider: str, provider_news_ids: Sequence[str]
    ) -> dict[str, PersistedNewsIntelligenceItem]:
        """Keyed by `provider_news_id` — only rows matching one of the
        given ids are returned (task scope §10: check before enriching,
        not a full-table scan)."""
        if not provider_news_ids:
            return {}
        result = await self._session.execute(
            select(NewsIntelligenceItemModel).where(
                NewsIntelligenceItemModel.ticker == ticker,
                NewsIntelligenceItemModel.news_provider == news_provider,
                NewsIntelligenceItemModel.provider_news_id.in_(provider_news_ids),
            )
        )
        return {model.provider_news_id: _to_domain(model) for model in result.scalars()}
