"""Unit tests for `evaluations.domain` — no DB, no HTTP (task scope §19)."""

from __future__ import annotations

from datetime import datetime, timezone

from trading_ai.evaluations.domain import (
    EvaluationNotFoundError,
    InsightEvaluation,
    InsightRating,
    InvalidOutcomeError,
)
from trading_ai.insights.domain import InsightNotFoundError

_T = datetime(2026, 3, 2, 14, 30, tzinfo=timezone.utc)


def test_insight_rating_has_exactly_three_categorical_values() -> None:
    """Product Owner decision: categorical 3-way, not binary, not
    numeric — a stable machine value, not a Russian UI string."""
    values = {member.value for member in InsightRating}
    assert values == {"useful", "partially_useful", "not_useful"}


def test_insight_rating_values_are_stable_machine_identifiers_not_prose() -> None:
    for member in InsightRating:
        assert member.value.islower()
        assert " " not in member.value
        assert not any(ch.isalpha() and ord(ch) > 127 for ch in member.value)


def test_insight_evaluation_carries_both_rating_and_outcome_halves() -> None:
    """FR-038: rating and outcome are two independently-settable halves
    of one record, not two separate entities."""
    evaluation = InsightEvaluation(
        id=1,
        insight_id=42,
        rating=InsightRating.USEFUL,
        rated_at=_T,
        outcome_note="Цена действительно выросла на 3%.",
        outcome_recorded_at=_T,
        created_at=_T,
        updated_at=None,
    )
    assert evaluation.insight_id == 42
    assert evaluation.rating is InsightRating.USEFUL
    assert evaluation.outcome_note == "Цена действительно выросла на 3%."


def test_insight_evaluation_allows_rating_without_outcome() -> None:
    """UJ-014 has no precondition on UJ-015 — a fresh rating with no
    outcome yet is a valid state."""
    evaluation = InsightEvaluation(
        id=1,
        insight_id=42,
        rating=InsightRating.PARTIALLY_USEFUL,
        rated_at=_T,
        outcome_note=None,
        outcome_recorded_at=None,
        created_at=_T,
        updated_at=None,
    )
    assert evaluation.outcome_note is None
    assert evaluation.outcome_recorded_at is None


def test_insight_evaluation_allows_outcome_without_rating() -> None:
    """UJ-015 has no precondition on UJ-014 — a recorded outcome with no
    rating yet is also a valid state."""
    evaluation = InsightEvaluation(
        id=1,
        insight_id=42,
        rating=None,
        rated_at=None,
        outcome_note="Инсайт не подтвердился.",
        outcome_recorded_at=_T,
        created_at=_T,
        updated_at=None,
    )
    assert evaluation.rating is None
    assert evaluation.outcome_note == "Инсайт не подтвердился."


def test_evaluation_not_found_error_carries_insight_id() -> None:
    error = EvaluationNotFoundError(42)
    assert error.insight_id == 42


def test_invalid_outcome_error_carries_reason() -> None:
    error = InvalidOutcomeError("outcome note must not be blank")
    assert "blank" in str(error)


def test_evaluations_reuses_insights_not_found_error_not_a_duplicate_type() -> None:
    """MODULE_BOUNDARIES.md §12: evaluations depends on insights only
    for existence-checking — reusing `InsightNotFoundError` (rather than
    defining a second, parallel "insight missing" error type) is a
    deliberate design choice, asserted here so it doesn't silently drift."""
    error = InsightNotFoundError(7)
    assert error.insight_id == 7
