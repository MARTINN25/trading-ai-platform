"""Concrete evaluation/outcome repository — no generic repository abstraction.

Owns no transaction boundary: whoever obtained the `AsyncSession`
(`trading_ai.infrastructure.database.session.session_scope`) decides
when to commit or roll back — this repository never calls `commit()`
(same rule as `insights.repository.InsightRepository`).

Only `get_by_insight_id`/`upsert_rating`/`upsert_outcome` exist — no
generic `save`/`delete`. "Upsert" here means "read the existing row for
this `insight_id`, if any; update the relevant half in place or insert
a new row" — never more than one row per `insight_id` (the `UNIQUE`
constraint on `insight_id` guarantees this even under a concurrent
insert race).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trading_ai.evaluations.domain import InsightEvaluation, InsightRating
from trading_ai.evaluations.models import InsightEvaluationModel


def _to_domain(model: InsightEvaluationModel) -> InsightEvaluation:
    return InsightEvaluation(
        id=model.id,
        insight_id=model.insight_id,
        rating=InsightRating(model.rating) if model.rating is not None else None,
        rated_at=model.rated_at,
        outcome_note=model.outcome_note,
        outcome_recorded_at=model.outcome_recorded_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class EvaluationRepository:
    """Concrete repository for `insight_evaluations` — no generic base class."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_insight_id(self, insight_id: int) -> InsightEvaluation | None:
        result = await self._session.execute(
            select(InsightEvaluationModel).where(
                InsightEvaluationModel.insight_id == insight_id
            )
        )
        model = result.scalar_one_or_none()
        return _to_domain(model) if model is not None else None

    async def upsert_rating(
        self, insight_id: int, rating: InsightRating, rated_at: datetime
    ) -> InsightEvaluation:
        model = await self._get_model(insight_id)
        if model is None:
            model = InsightEvaluationModel(insight_id=insight_id)
            self._session.add(model)
        else:
            model.updated_at = rated_at
        model.rating = rating.value
        model.rated_at = rated_at
        await self._session.flush()
        return _to_domain(model)

    async def upsert_outcome(
        self, insight_id: int, outcome_note: str, outcome_recorded_at: datetime
    ) -> InsightEvaluation:
        model = await self._get_model(insight_id)
        if model is None:
            model = InsightEvaluationModel(insight_id=insight_id)
            self._session.add(model)
        else:
            model.updated_at = outcome_recorded_at
        model.outcome_note = outcome_note
        model.outcome_recorded_at = outcome_recorded_at
        await self._session.flush()
        return _to_domain(model)

    async def _get_model(self, insight_id: int) -> InsightEvaluationModel | None:
        result = await self._session.execute(
            select(InsightEvaluationModel).where(
                InsightEvaluationModel.insight_id == insight_id
            )
        )
        return result.scalar_one_or_none()
