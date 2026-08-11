"""Concrete insight repository — no generic repository abstraction.

Owns no transaction boundary: whoever obtained the `AsyncSession`
(`trading_ai.infrastructure.database.session.session_scope`) decides
when to commit or roll back — this repository never calls `commit()`
(same rule as `watchlist.repository.WatchlistRepository`).

Only `add`/`list_recent_for_ticker`/`get_by_id` exist — no update, no
delete (task scope §10, §29; ADR-0004 §20 immutability).
"""

from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from trading_ai.ai.types import ConfidenceLevel, KeyFact
from trading_ai.insights.domain import MAX_HISTORY_ITEMS, NewInsight, SavedInsight
from trading_ai.insights.models import InsightModel


def _to_domain(model: InsightModel) -> SavedInsight:
    return SavedInsight(
        id=model.id,
        ticker=model.ticker,
        generated_at=model.generated_at,
        created_at=model.created_at,
        summary=model.summary,
        price_context=model.price_context,
        news_context=model.news_context,
        key_facts=tuple(
            KeyFact(fact=item["fact"], source=item["source"]) for item in model.key_facts
        ),
        insight_hypothesis=model.insight_hypothesis,
        confidence=ConfidenceLevel(model.confidence),
        confidence_reason=model.confidence_reason,
        considerations=tuple(model.considerations),
        risks=tuple(model.risks),
        key_drivers=tuple(model.key_drivers),
        data_freshness=model.data_freshness,
        source_data_as_of=model.source_data_as_of,
        disclaimer=model.disclaimer,
        provider=model.provider,
        model=model.model,
        prompt_version=model.prompt_version,
        schema_version=model.schema_version,
    )


class InsightRepository:
    """Concrete repository for `insights` — no generic base class."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, insight: NewInsight) -> SavedInsight:
        model = InsightModel(
            ticker=insight.ticker,
            generated_at=insight.generated_at,
            summary=insight.summary,
            price_context=insight.price_context,
            news_context=insight.news_context,
            key_facts=[{"fact": fact.fact, "source": fact.source} for fact in insight.key_facts],
            insight_hypothesis=insight.insight_hypothesis,
            confidence=insight.confidence.value,
            confidence_reason=insight.confidence_reason,
            considerations=list(insight.considerations),
            risks=list(insight.risks),
            key_drivers=list(insight.key_drivers),
            data_freshness=insight.data_freshness,
            source_data_as_of=insight.source_data_as_of,
            disclaimer=insight.disclaimer,
            provider=insight.provider,
            model=insight.model,
            prompt_version=insight.prompt_version,
            schema_version=insight.schema_version,
        )
        self._session.add(model)
        await self._session.flush()
        return _to_domain(model)

    async def list_recent_for_ticker(
        self, ticker: str, limit: int = MAX_HISTORY_ITEMS
    ) -> list[SavedInsight]:
        """Newest-first, bounded (task scope §14)."""
        result = await self._session.execute(
            select(InsightModel)
            .where(InsightModel.ticker == ticker)
            .order_by(desc(InsightModel.created_at), desc(InsightModel.id))
            .limit(limit)
        )
        return [_to_domain(model) for model in result.scalars()]

    async def get_by_id(self, insight_id: int) -> SavedInsight | None:
        result = await self._session.execute(
            select(InsightModel).where(InsightModel.id == insight_id)
        )
        model = result.scalar_one_or_none()
        return _to_domain(model) if model is not None else None
