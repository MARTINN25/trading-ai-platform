"""User evaluation / manual outcome application use cases.

Every use case here first confirms the referenced insight actually
exists via `_InsightLookup` (implemented by
`trading_ai.insights.repository.InsightRepository`, only its
read-only `get_by_id` — MODULE_BOUNDARIES.md §12: "insights — только
для ссылки на инсайт, не для его изменения") before touching the
evaluation row. None of these use cases ever read or write insight
*content* — only `insight_id` is used, so there is no path by which a
caller could smuggle in altered insight text/provenance through this
module (task scope §13: "нельзя подделать insight content/provenance").
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from trading_ai.evaluations.domain import (
    EvaluationNotFoundError,
    InsightEvaluation,
    InsightRating,
    InvalidOutcomeError,
)
from trading_ai.insights.domain import InsightNotFoundError

_MAX_OUTCOME_NOTE_LENGTH = 2000


class _InsightLookup(Protocol):
    async def get_by_id(self, insight_id: int) -> object | None: ...


class _EvaluationRepositoryLike(Protocol):
    async def get_by_insight_id(self, insight_id: int) -> InsightEvaluation | None: ...

    async def upsert_rating(
        self, insight_id: int, rating: InsightRating, rated_at: datetime
    ) -> InsightEvaluation: ...

    async def upsert_outcome(
        self, insight_id: int, outcome_note: str, outcome_recorded_at: datetime
    ) -> InsightEvaluation: ...


async def _require_insight(insight_lookup: _InsightLookup, insight_id: int) -> None:
    insight = await insight_lookup.get_by_id(insight_id)
    if insight is None:
        raise InsightNotFoundError(insight_id)


class EvaluateInsight:
    """Sets (or replaces — UJ-014's "изменение ранее выставленной
    оценки") the rating half of the evaluation record."""

    def __init__(
        self, repository: _EvaluationRepositoryLike, insight_lookup: _InsightLookup
    ) -> None:
        self._repository = repository
        self._insight_lookup = insight_lookup

    async def execute(self, insight_id: int, rating: InsightRating) -> InsightEvaluation:
        await _require_insight(self._insight_lookup, insight_id)
        return await self._repository.upsert_rating(insight_id, rating, datetime.now(UTC))


class RecordInsightOutcome:
    """Sets (or replaces) the manual-outcome half of the evaluation
    record (FR-036) — independent of whether a rating exists yet (UJ-015
    has no precondition on UJ-014)."""

    def __init__(
        self, repository: _EvaluationRepositoryLike, insight_lookup: _InsightLookup
    ) -> None:
        self._repository = repository
        self._insight_lookup = insight_lookup

    async def execute(self, insight_id: int, outcome_note: str) -> InsightEvaluation:
        note = outcome_note.strip()
        if not note:
            raise InvalidOutcomeError("outcome note must not be blank")
        if len(note) > _MAX_OUTCOME_NOTE_LENGTH:
            raise InvalidOutcomeError(
                f"outcome note must not exceed {_MAX_OUTCOME_NOTE_LENGTH} characters"
            )
        await _require_insight(self._insight_lookup, insight_id)
        return await self._repository.upsert_outcome(insight_id, note, datetime.now(UTC))


class GetInsightEvaluation:
    def __init__(
        self, repository: _EvaluationRepositoryLike, insight_lookup: _InsightLookup
    ) -> None:
        self._repository = repository
        self._insight_lookup = insight_lookup

    async def execute(self, insight_id: int) -> InsightEvaluation:
        evaluation = await self._repository.get_by_insight_id(insight_id)
        if evaluation is not None:
            return evaluation
        # Not found: distinguish "insight itself doesn't exist" (404,
        # InsightNotFoundError) from "insight exists but was never
        # evaluated" (404, EvaluationNotFoundError) — only worth the
        # extra lookup once the cheaper evaluation query has already
        # come back empty.
        await _require_insight(self._insight_lookup, insight_id)
        raise EvaluationNotFoundError(insight_id)
