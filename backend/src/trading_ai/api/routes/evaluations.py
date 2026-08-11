"""Insight evaluation / manual outcome HTTP endpoints — thin transport
layer only (ADR-0002 §17), same as `api.routes.watchlist`/
`api.routes.instruments`.

**Not the developer AI quality harness.** `trading_ai.ai.evaluation`
(CLI, `python -m trading_ai.ai.evaluation`) scores the LLM's structured
*output* against a fixed dataset and has no HTTP surface at all. This
module exposes the opposite: a real end user rating one specific
already-saved insight and optionally recording a manual outcome
(`trading_ai.evaluations`, FR-035/FR-036/FR-038).

The client can only ever send a rating value or an outcome note — never
insight content or provenance (task scope §14): `EvaluateInsightRequest`
and `RecordOutcomeRequest` each accept exactly one field, `extra="forbid"`.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading_ai.evaluations.domain import (
    EvaluationNotFoundError,
    InsightEvaluation,
    InsightRating,
    InvalidOutcomeError,
)
from trading_ai.evaluations.repository import EvaluationRepository
from trading_ai.evaluations.use_cases import (
    EvaluateInsight,
    GetInsightEvaluation,
    RecordInsightOutcome,
)
from trading_ai.infrastructure.database.session import session_scope
from trading_ai.insights.repository import InsightRepository

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_OUTCOME_NOTE_LENGTH = 2000


class EvaluateInsightRequest(BaseModel):
    """The *only* field this endpoint accepts (task scope §14)."""

    model_config = ConfigDict(extra="forbid")

    rating: InsightRating


class RecordOutcomeRequest(BaseModel):
    """The *only* field this endpoint accepts (task scope §14, §18: no
    entry price/exit price/quantity/side/commission/broker/P&L/position —
    this is not a trade journal)."""

    model_config = ConfigDict(extra="forbid")

    outcome_note: str = Field(min_length=1, max_length=_MAX_OUTCOME_NOTE_LENGTH)


class InsightEvaluationResponse(BaseModel):
    insight_id: int
    rating: InsightRating | None
    rated_at: datetime | None
    outcome_note: str | None
    outcome_recorded_at: datetime | None
    created_at: datetime
    updated_at: datetime | None


def _to_response(evaluation: InsightEvaluation) -> InsightEvaluationResponse:
    return InsightEvaluationResponse(
        insight_id=evaluation.insight_id,
        rating=evaluation.rating,
        rated_at=evaluation.rated_at,
        outcome_note=evaluation.outcome_note,
        outcome_recorded_at=evaluation.outcome_recorded_at,
        created_at=evaluation.created_at,
        updated_at=evaluation.updated_at,
    )


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    """Duplicated (not imported) from `api.routes.watchlist`/
    `api.routes.instruments` — same reasoning as those modules'
    identical helper: this route module has no other reason to depend
    on either of them."""
    factory = getattr(request.app.state, "db_session_factory", None)
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database is not configured",
        )
    return factory  # type: ignore[no-any-return]


async def get_db_session(
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> AsyncIterator[AsyncSession]:
    """One session per request, one short transaction — same pattern as
    `api.routes.watchlist.get_db_session`."""
    async with session_scope(factory) as session:
        yield session


def get_evaluation_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EvaluationRepository:
    return EvaluationRepository(session)


def get_insight_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> InsightRepository:
    return InsightRepository(session)


def get_evaluate_insight_use_case(
    evaluation_repository: Annotated[EvaluationRepository, Depends(get_evaluation_repository)],
    insight_repository: Annotated[InsightRepository, Depends(get_insight_repository)],
) -> EvaluateInsight:
    return EvaluateInsight(evaluation_repository, insight_repository)


def get_record_insight_outcome_use_case(
    evaluation_repository: Annotated[EvaluationRepository, Depends(get_evaluation_repository)],
    insight_repository: Annotated[InsightRepository, Depends(get_insight_repository)],
) -> RecordInsightOutcome:
    return RecordInsightOutcome(evaluation_repository, insight_repository)


def get_insight_evaluation_use_case(
    evaluation_repository: Annotated[EvaluationRepository, Depends(get_evaluation_repository)],
    insight_repository: Annotated[InsightRepository, Depends(get_insight_repository)],
) -> GetInsightEvaluation:
    return GetInsightEvaluation(evaluation_repository, insight_repository)


@router.put("/insights/{insight_id}/evaluation", response_model=InsightEvaluationResponse)
async def evaluate_insight(
    insight_id: int,
    payload: EvaluateInsightRequest,
    use_case: Annotated[EvaluateInsight, Depends(get_evaluate_insight_use_case)],
) -> InsightEvaluationResponse:
    """Idempotent upsert (PUT, not POST) — UJ-014 explicitly allows the
    user to change a previously given rating; calling this twice with a
    different value simply replaces it, never creates a duplicate
    record (the `UNIQUE` constraint on `insight_id` makes a second row
    impossible regardless)."""
    started = time.monotonic()
    status_label = "error"
    try:
        evaluation = await use_case.execute(insight_id, payload.rating)
        status_label = "ok"
        return _to_response(evaluation)
    finally:
        logger.info(
            "operation=evaluate_insight insight_id=%s rating=%s status=%s latency_ms=%.1f",
            insight_id,
            payload.rating.value,
            status_label,
            (time.monotonic() - started) * 1000,
        )


@router.get("/insights/{insight_id}/evaluation", response_model=InsightEvaluationResponse)
async def get_insight_evaluation(
    insight_id: int,
    use_case: Annotated[GetInsightEvaluation, Depends(get_insight_evaluation_use_case)],
) -> InsightEvaluationResponse:
    evaluation = await use_case.execute(insight_id)
    return _to_response(evaluation)


@router.put("/insights/{insight_id}/outcome", response_model=InsightEvaluationResponse)
async def record_insight_outcome(
    insight_id: int,
    payload: RecordOutcomeRequest,
    use_case: Annotated[RecordInsightOutcome, Depends(get_record_insight_outcome_use_case)],
) -> InsightEvaluationResponse:
    """Idempotent upsert (PUT), independent of whether a rating exists
    yet (UJ-015 has no precondition on UJ-014). Never logs the free-text
    `outcome_note` itself (task scope §26)."""
    started = time.monotonic()
    status_label = "error"
    try:
        evaluation = await use_case.execute(insight_id, payload.outcome_note)
        status_label = "ok"
        return _to_response(evaluation)
    finally:
        logger.info(
            "operation=record_insight_outcome insight_id=%s status=%s latency_ms=%.1f",
            insight_id,
            status_label,
            (time.monotonic() - started) * 1000,
        )


def register_evaluation_exception_handlers(app: FastAPI) -> None:
    """`InsightNotFoundError` is already handled globally by
    `api.routes.instruments.register_insight_exception_handlers` (404) —
    FastAPI exception handlers apply app-wide, not per router, so it is
    not re-registered here."""

    @app.exception_handler(EvaluationNotFoundError)
    async def _handle_evaluation_not_found(
        _request: Request, _exc: EvaluationNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "no evaluation recorded for this insight yet"},
        )

    @app.exception_handler(InvalidOutcomeError)
    async def _handle_invalid_outcome(_request: Request, _exc: InvalidOutcomeError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": "invalid outcome note"},
        )
