"""Use-case tests for `evaluations.use_cases` — fake repositories only,
no DB/HTTP (task scope §21)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from trading_ai.evaluations.domain import (
    EvaluationNotFoundError,
    InsightEvaluation,
    InsightRating,
    InvalidOutcomeError,
)
from trading_ai.evaluations.use_cases import (
    EvaluateInsight,
    GetInsightEvaluation,
    RecordInsightOutcome,
)
from trading_ai.insights.domain import InsightNotFoundError

_T = datetime(2026, 3, 2, 14, 30, tzinfo=timezone.utc)


class _FakeInsight:
    def __init__(self, insight_id: int) -> None:
        self.id = insight_id


class FakeInsightLookup:
    def __init__(self, existing_ids: set[int]) -> None:
        self._existing_ids = existing_ids

    async def get_by_id(self, insight_id: int) -> _FakeInsight | None:
        return _FakeInsight(insight_id) if insight_id in self._existing_ids else None


class FakeEvaluationRepository:
    def __init__(self) -> None:
        self._rows: dict[int, InsightEvaluation] = {}
        self._next_id = 1

    async def get_by_insight_id(self, insight_id: int) -> InsightEvaluation | None:
        return self._rows.get(insight_id)

    async def upsert_rating(
        self, insight_id: int, rating: InsightRating, rated_at: datetime
    ) -> InsightEvaluation:
        existing = self._rows.get(insight_id)
        row = InsightEvaluation(
            id=existing.id if existing else self._alloc_id(),
            insight_id=insight_id,
            rating=rating,
            rated_at=rated_at,
            outcome_note=existing.outcome_note if existing else None,
            outcome_recorded_at=existing.outcome_recorded_at if existing else None,
            created_at=existing.created_at if existing else rated_at,
            updated_at=rated_at if existing else None,
        )
        self._rows[insight_id] = row
        return row

    async def upsert_outcome(
        self, insight_id: int, outcome_note: str, outcome_recorded_at: datetime
    ) -> InsightEvaluation:
        existing = self._rows.get(insight_id)
        row = InsightEvaluation(
            id=existing.id if existing else self._alloc_id(),
            insight_id=insight_id,
            rating=existing.rating if existing else None,
            rated_at=existing.rated_at if existing else None,
            outcome_note=outcome_note,
            outcome_recorded_at=outcome_recorded_at,
            created_at=existing.created_at if existing else outcome_recorded_at,
            updated_at=outcome_recorded_at if existing else None,
        )
        self._rows[insight_id] = row
        return row

    def _alloc_id(self) -> int:
        row_id = self._next_id
        self._next_id += 1
        return row_id


@pytest.mark.anyio
async def test_evaluate_insight_success() -> None:
    repository = FakeEvaluationRepository()
    use_case = EvaluateInsight(repository, FakeInsightLookup({1}))

    result = await use_case.execute(1, InsightRating.USEFUL)

    assert result.insight_id == 1
    assert result.rating is InsightRating.USEFUL
    assert result.rated_at is not None


@pytest.mark.anyio
async def test_evaluate_insight_missing_insight_raises() -> None:
    repository = FakeEvaluationRepository()
    use_case = EvaluateInsight(repository, FakeInsightLookup(set()))

    with pytest.raises(InsightNotFoundError):
        await use_case.execute(999, InsightRating.USEFUL)


@pytest.mark.anyio
async def test_evaluate_insight_replaces_previous_rating() -> None:
    """UJ-014's "изменение ранее выставленной оценки" — upsert, not append."""
    repository = FakeEvaluationRepository()
    use_case = EvaluateInsight(repository, FakeInsightLookup({1}))

    await use_case.execute(1, InsightRating.NOT_USEFUL)
    result = await use_case.execute(1, InsightRating.USEFUL)

    assert result.rating is InsightRating.USEFUL
    assert result.updated_at is not None


@pytest.mark.anyio
async def test_record_outcome_success() -> None:
    repository = FakeEvaluationRepository()
    use_case = RecordInsightOutcome(repository, FakeInsightLookup({1}))

    result = await use_case.execute(1, "Цена выросла на 3%, инсайт подтвердился.")

    assert result.outcome_note == "Цена выросла на 3%, инсайт подтвердился."
    assert result.outcome_recorded_at is not None


@pytest.mark.anyio
async def test_record_outcome_does_not_require_prior_evaluation() -> None:
    """UJ-015 has no precondition on UJ-014."""
    repository = FakeEvaluationRepository()
    use_case = RecordInsightOutcome(repository, FakeInsightLookup({1}))

    result = await use_case.execute(1, "Результат зафиксирован без оценки.")

    assert result.rating is None
    assert result.outcome_note == "Результат зафиксирован без оценки."


@pytest.mark.anyio
async def test_record_outcome_missing_insight_raises() -> None:
    repository = FakeEvaluationRepository()
    use_case = RecordInsightOutcome(repository, FakeInsightLookup(set()))

    with pytest.raises(InsightNotFoundError):
        await use_case.execute(999, "Результат.")


@pytest.mark.anyio
async def test_record_outcome_blank_note_raises_before_insight_lookup() -> None:
    repository = FakeEvaluationRepository()
    use_case = RecordInsightOutcome(repository, FakeInsightLookup(set()))

    with pytest.raises(InvalidOutcomeError):
        await use_case.execute(1, "   ")


@pytest.mark.anyio
async def test_record_outcome_too_long_note_raises() -> None:
    repository = FakeEvaluationRepository()
    use_case = RecordInsightOutcome(repository, FakeInsightLookup({1}))

    with pytest.raises(InvalidOutcomeError):
        await use_case.execute(1, "x" * 2001)


@pytest.mark.anyio
async def test_record_outcome_replaces_previous_outcome() -> None:
    repository = FakeEvaluationRepository()
    use_case = RecordInsightOutcome(repository, FakeInsightLookup({1}))

    await use_case.execute(1, "Первая запись.")
    result = await use_case.execute(1, "Исправленная запись.")

    assert result.outcome_note == "Исправленная запись."
    assert result.updated_at is not None


@pytest.mark.anyio
async def test_get_insight_evaluation_found() -> None:
    repository = FakeEvaluationRepository()
    lookup = FakeInsightLookup({1})
    await EvaluateInsight(repository, lookup).execute(1, InsightRating.USEFUL)
    use_case = GetInsightEvaluation(repository, lookup)

    result = await use_case.execute(1)

    assert result.rating is InsightRating.USEFUL


@pytest.mark.anyio
async def test_get_insight_evaluation_missing_insight_raises_insight_not_found() -> None:
    repository = FakeEvaluationRepository()
    use_case = GetInsightEvaluation(repository, FakeInsightLookup(set()))

    with pytest.raises(InsightNotFoundError):
        await use_case.execute(999)


@pytest.mark.anyio
async def test_get_insight_evaluation_existing_insight_never_evaluated_raises_evaluation_not_found() -> None:
    """Distinguishes "insight doesn't exist" from "insight exists but
    was never rated/outcome-recorded" — both surface as 404 at the API
    layer but with different domain errors/messages."""
    repository = FakeEvaluationRepository()
    use_case = GetInsightEvaluation(repository, FakeInsightLookup({1}))

    with pytest.raises(EvaluationNotFoundError):
        await use_case.execute(1)


@pytest.mark.anyio
async def test_use_cases_never_touch_insight_content() -> None:
    """Structural guard (task scope §13): `FakeInsightLookup` only ever
    exposes an id — there is no attribute path by which these use cases
    could read or forward insight text/provenance."""
    repository = FakeEvaluationRepository()
    lookup = FakeInsightLookup({1})
    assert not hasattr(_FakeInsight(1), "summary")
    assert not hasattr(_FakeInsight(1), "provider")
    await EvaluateInsight(repository, lookup).execute(1, InsightRating.USEFUL)
