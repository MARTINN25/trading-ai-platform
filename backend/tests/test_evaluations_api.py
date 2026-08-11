"""API-boundary tests for insight evaluation/outcome endpoints (task
scope §22). Overrides use cases directly — no httpx/asyncpg."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from trading_ai.api.routes.evaluations import (
    get_evaluate_insight_use_case,
    get_insight_evaluation_use_case,
    get_record_insight_outcome_use_case,
)
from trading_ai.evaluations.domain import (
    EvaluationNotFoundError,
    InsightEvaluation,
    InsightRating,
    InvalidOutcomeError,
)
from trading_ai.insights.domain import InsightNotFoundError
from trading_ai.main import create_app

_T = datetime(2026, 3, 2, 14, 30, tzinfo=timezone.utc)


def _evaluation(
    insight_id: int = 1,
    rating: InsightRating | None = InsightRating.USEFUL,
    outcome_note: str | None = None,
) -> InsightEvaluation:
    return InsightEvaluation(
        id=1,
        insight_id=insight_id,
        rating=rating,
        rated_at=_T if rating is not None else None,
        outcome_note=outcome_note,
        outcome_recorded_at=_T if outcome_note is not None else None,
        created_at=_T,
        updated_at=None,
    )


class _FakeEvaluateInsight:
    def __init__(self, result: InsightEvaluation | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.received: tuple[int, InsightRating] | None = None

    async def execute(self, insight_id: int, rating: InsightRating) -> InsightEvaluation:
        self.received = (insight_id, rating)
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


class _FakeRecordInsightOutcome:
    def __init__(self, result: InsightEvaluation | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.received: tuple[int, str] | None = None

    async def execute(self, insight_id: int, outcome_note: str) -> InsightEvaluation:
        self.received = (insight_id, outcome_note)
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


class _FakeGetInsightEvaluation:
    def __init__(self, result: InsightEvaluation | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    async def execute(self, insight_id: int) -> InsightEvaluation:
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def _override_evaluate(app: FastAPI, fake: _FakeEvaluateInsight) -> None:
    app.dependency_overrides[get_evaluate_insight_use_case] = lambda: fake


def _override_outcome(app: FastAPI, fake: _FakeRecordInsightOutcome) -> None:
    app.dependency_overrides[get_record_insight_outcome_use_case] = lambda: fake


def _override_get(app: FastAPI, fake: _FakeGetInsightEvaluation) -> None:
    app.dependency_overrides[get_insight_evaluation_use_case] = lambda: fake


def test_evaluate_insight_success() -> None:
    app = create_app()
    fake = _FakeEvaluateInsight(result=_evaluation())
    _override_evaluate(app, fake)
    client = TestClient(app)

    response = client.put("/insights/1/evaluation", json={"rating": "useful"})

    assert response.status_code == 200
    body = response.json()
    assert body["insight_id"] == 1
    assert body["rating"] == "useful"
    assert fake.received == (1, InsightRating.USEFUL)


def test_evaluate_insight_invalid_rating_value_returns_422() -> None:
    app = create_app()
    _override_evaluate(app, _FakeEvaluateInsight(result=_evaluation()))
    client = TestClient(app)

    response = client.put("/insights/1/evaluation", json={"rating": "amazing"})

    assert response.status_code == 422


def test_evaluate_insight_rejects_extra_body_fields() -> None:
    """No arbitrary insight content/provenance accepted from the
    frontend (task scope §14)."""
    app = create_app()
    _override_evaluate(app, _FakeEvaluateInsight(result=_evaluation()))
    client = TestClient(app)

    response = client.put(
        "/insights/1/evaluation",
        json={"rating": "useful", "provider": "not-xai", "summary": "fabricated"},
    )

    assert response.status_code == 422


def test_evaluate_insight_missing_insight_returns_404() -> None:
    app = create_app()
    _override_evaluate(app, _FakeEvaluateInsight(error=InsightNotFoundError(999)))
    client = TestClient(app)

    response = client.put("/insights/999/evaluation", json={"rating": "useful"})

    assert response.status_code == 404


def test_get_insight_evaluation_success() -> None:
    app = create_app()
    _override_get(app, _FakeGetInsightEvaluation(result=_evaluation(rating=InsightRating.PARTIALLY_USEFUL)))
    client = TestClient(app)

    response = client.get("/insights/1/evaluation")

    assert response.status_code == 200
    assert response.json()["rating"] == "partially_useful"


def test_get_insight_evaluation_missing_insight_returns_404() -> None:
    app = create_app()
    _override_get(app, _FakeGetInsightEvaluation(error=InsightNotFoundError(999)))
    client = TestClient(app)

    response = client.get("/insights/999/evaluation")

    assert response.status_code == 404


def test_get_insight_evaluation_not_yet_evaluated_returns_404() -> None:
    app = create_app()
    _override_get(app, _FakeGetInsightEvaluation(error=EvaluationNotFoundError(1)))
    client = TestClient(app)

    response = client.get("/insights/1/evaluation")

    assert response.status_code == 404
    assert "not" in response.json()["detail"].lower() or "evaluat" in response.json()["detail"].lower()


def test_record_outcome_success() -> None:
    app = create_app()
    fake = _FakeRecordInsightOutcome(result=_evaluation(outcome_note="Подтвердилось."))
    _override_outcome(app, fake)
    client = TestClient(app)

    response = client.put("/insights/1/outcome", json={"outcome_note": "Подтвердилось."})

    assert response.status_code == 200
    assert response.json()["outcome_note"] == "Подтвердилось."
    assert fake.received == (1, "Подтвердилось.")


def test_record_outcome_invalid_blank_note_returns_422() -> None:
    app = create_app()
    _override_outcome(app, _FakeRecordInsightOutcome(error=InvalidOutcomeError("blank")))
    client = TestClient(app)

    response = client.put("/insights/1/outcome", json={"outcome_note": "irrelevant"})

    assert response.status_code == 422


def test_record_outcome_missing_field_returns_422() -> None:
    app = create_app()
    _override_outcome(app, _FakeRecordInsightOutcome(result=_evaluation()))
    client = TestClient(app)

    response = client.put("/insights/1/outcome", json={})

    assert response.status_code == 422


def test_record_outcome_missing_insight_returns_404() -> None:
    app = create_app()
    _override_outcome(app, _FakeRecordInsightOutcome(error=InsightNotFoundError(999)))
    client = TestClient(app)

    response = client.put("/insights/999/outcome", json={"outcome_note": "x"})

    assert response.status_code == 404


def test_record_outcome_rejects_extra_body_fields() -> None:
    """Not a Trade Journal (task scope §18) — entry/exit price,
    quantity, side etc. are not accepted fields at all."""
    app = create_app()
    _override_outcome(app, _FakeRecordInsightOutcome(result=_evaluation()))
    client = TestClient(app)

    response = client.put(
        "/insights/1/outcome",
        json={"outcome_note": "x", "entry_price": 100, "quantity": 10, "side": "long"},
    )

    assert response.status_code == 422


def test_evaluation_endpoints_without_database_configured_return_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TRADING_AI_DATABASE_URL", raising=False)
    app = create_app()
    with TestClient(app) as client:
        evaluate_response = client.put("/insights/1/evaluation", json={"rating": "useful"})
        get_response = client.get("/insights/1/evaluation")
        outcome_response = client.put("/insights/1/outcome", json={"outcome_note": "x"})

    assert evaluate_response.status_code == 503
    assert get_response.status_code == 503
    assert outcome_response.status_code == 503
    for response in (evaluate_response, get_response, outcome_response):
        assert "sql" not in response.text.lower()
        assert "traceback" not in response.text.lower()


def test_evaluate_insight_response_never_contains_secrets() -> None:
    app = create_app()
    _override_evaluate(app, _FakeEvaluateInsight(result=_evaluation()))
    client = TestClient(app)

    response = client.put("/insights/1/evaluation", json={"rating": "useful"})

    assert "api.x.ai" not in response.text
    assert "TRADING_AI" not in response.text
