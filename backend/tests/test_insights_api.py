"""API-boundary tests for the insight save/history/detail endpoints
(task scope §22). Overrides use cases directly — no httpx/asyncpg."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from trading_ai.ai.types import ConfidenceLevel, InstrumentAnalysis, KeyFact
from trading_ai.api.routes.instruments import (
    get_generate_instrument_analysis_use_case,
    get_insight_detail_use_case,
    get_insight_repository,
    get_list_instrument_insights_use_case,
    get_save_insight_use_case,
)
from trading_ai.insights.domain import (
    InsightNotFoundError,
    NewInsight,
    PendingAnalysisNotFoundError,
    SavedInsight,
)
from trading_ai.main import create_app
from trading_ai.watchlist.domain import InvalidTickerError

_T = datetime(2026, 3, 2, 14, 30, tzinfo=timezone.utc)
_FAKE_LLM_API_KEY = "test-xai-secret-should-never-leak"


def _sample_analysis(ticker: str = "AAPL") -> InstrumentAnalysis:
    return InstrumentAnalysis(
        ticker=ticker,
        generated_at=_T,
        summary="Краткий вывод.",
        price_context="Цена выросла.",
        news_context="Новости нейтральные.",
        key_facts=(KeyFact(fact="Цена выросла.", source="Текущая котировка"),),
        insight_hypothesis="Рост может продолжиться.",
        confidence=ConfidenceLevel.MEDIUM,
        confidence_reason="Данные ограничены.",
        considerations=("Стоит проверить дальнейшую динамику.",),
        risks=("Риск сохраняется.",),
        key_drivers=("Рост цены.",),
        data_freshness="котировка актуальна.",
        source_data_as_of=_T,
        disclaimer="AI-анализ носит информационный характер и не является инвестиционной рекомендацией.",
        provider="xai",
        model="grok-4.5",
        prompt_version="instrument-analysis-v2",
        schema_version="insight-structure-v1",
    )


def _sample_saved_insight(insight_id: int = 1, ticker: str = "AAPL") -> SavedInsight:
    analysis = _sample_analysis(ticker)
    return SavedInsight(
        id=insight_id,
        ticker=analysis.ticker,
        generated_at=analysis.generated_at,
        created_at=_T,
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


class _FakeGenerateInstrumentAnalysis:
    def __init__(self, result: InstrumentAnalysis) -> None:
        self._result = result

    async def execute(self, raw_ticker: str) -> InstrumentAnalysis:
        return self._result


class _FakeSaveInsight:
    def __init__(self, result: SavedInsight | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.received: tuple[str, str] | None = None

    async def execute(self, raw_ticker: str, analysis_token: str) -> SavedInsight:
        self.received = (raw_ticker, analysis_token)
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


class _FakeListInstrumentInsights:
    def __init__(self, result: list[SavedInsight]) -> None:
        self._result = result

    async def execute(self, raw_ticker: str) -> list[SavedInsight]:
        return self._result


class _FakeGetInsightDetail:
    def __init__(self, result: SavedInsight | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    async def execute(self, insight_id: int) -> SavedInsight:
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


class _FakeInsightRepository:
    """Real `SaveInsight`/`ListInstrumentInsights`/`GetInsightDetail` use
    cases run against this fake — only the repository (DB boundary) and
    the generation use case are faked, so the real pending-analysis
    token round-trip is exercised end-to-end at the HTTP layer without
    a real database."""

    def __init__(self) -> None:
        self.added: list[NewInsight] = []
        self._next_id = 1
        self._rows: dict[int, SavedInsight] = {}

    async def add(self, insight: NewInsight) -> SavedInsight:
        self.added.append(insight)
        saved = _sample_saved_insight(insight_id=self._next_id, ticker=insight.ticker)
        self._rows[self._next_id] = saved
        self._next_id += 1
        return saved

    async def list_recent_for_ticker(self, ticker: str) -> list[SavedInsight]:
        return [row for row in self._rows.values() if row.ticker == ticker]

    async def get_by_id(self, insight_id: int) -> SavedInsight | None:
        return self._rows.get(insight_id)


def _override_save(app: FastAPI, fake: _FakeSaveInsight) -> None:
    app.dependency_overrides[get_save_insight_use_case] = lambda: fake


def _override_list(app: FastAPI, fake: _FakeListInstrumentInsights) -> None:
    app.dependency_overrides[get_list_instrument_insights_use_case] = lambda: fake


def _override_detail(app: FastAPI, fake: _FakeGetInsightDetail) -> None:
    app.dependency_overrides[get_insight_detail_use_case] = lambda: fake


def test_save_insight_success_returns_201_with_full_structure() -> None:
    app = create_app()
    fake = _FakeSaveInsight(result=_sample_saved_insight())
    _override_save(app, fake)
    client = TestClient(app)

    response = client.post("/instruments/AAPL/insights", json={"analysis_token": "tok-1"})

    assert response.status_code == 201
    body = response.json()
    assert body["ticker"] == "AAPL"
    assert body["id"] == 1
    assert body["key_facts"] == [{"fact": "Цена выросла.", "source": "Текущая котировка"}]
    assert body["confidence"] == "medium"
    assert body["prompt_version"] == "instrument-analysis-v2"
    assert body["schema_version"] == "insight-structure-v1"
    assert fake.received == ("AAPL", "tok-1")


def test_save_insight_unknown_token_returns_404() -> None:
    app = create_app()
    _override_save(app, _FakeSaveInsight(error=PendingAnalysisNotFoundError("AAPL")))
    client = TestClient(app)

    response = client.post("/instruments/AAPL/insights", json={"analysis_token": "bad-token"})

    assert response.status_code == 404


def test_save_insight_invalid_ticker_returns_422() -> None:
    app = create_app()
    _override_save(app, _FakeSaveInsight(error=InvalidTickerError("ticker must not be empty")))
    client = TestClient(app)

    response = client.post("/instruments/ /insights", json={"analysis_token": "tok-1"})

    assert response.status_code == 422


def test_save_insight_rejects_extra_body_fields() -> None:
    """No arbitrary provenance accepted from the frontend (task scope
    §12/§22) — `provider`/`summary`/etc are not part of the request
    schema and are explicitly rejected, not silently ignored."""
    app = create_app()
    _override_save(app, _FakeSaveInsight(result=_sample_saved_insight()))
    client = TestClient(app)

    response = client.post(
        "/instruments/AAPL/insights",
        json={"analysis_token": "tok-1", "provider": "not-xai", "summary": "fabricated"},
    )

    assert response.status_code == 422


def test_save_insight_missing_token_returns_422() -> None:
    app = create_app()
    _override_save(app, _FakeSaveInsight(result=_sample_saved_insight()))
    client = TestClient(app)

    response = client.post("/instruments/AAPL/insights", json={})

    assert response.status_code == 422


def test_list_instrument_insights_success() -> None:
    app = create_app()
    _override_list(app, _FakeListInstrumentInsights(result=[_sample_saved_insight()]))
    client = TestClient(app)

    response = client.get("/instruments/AAPL/insights")

    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "AAPL"
    assert len(body["items"]) == 1
    assert body["items"][0]["confidence"] == "medium"
    # Compact summary item — no key_facts/price_context/etc (task scope §14).
    assert "key_facts" not in body["items"][0]
    assert "price_context" not in body["items"][0]


def test_list_instrument_insights_empty_history() -> None:
    app = create_app()
    _override_list(app, _FakeListInstrumentInsights(result=[]))
    client = TestClient(app)

    response = client.get("/instruments/AAPL/insights")

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_get_insight_detail_success() -> None:
    app = create_app()
    _override_detail(app, _FakeGetInsightDetail(result=_sample_saved_insight()))
    client = TestClient(app)

    response = client.get("/insights/1")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == 1
    assert body["insight_hypothesis"] == "Рост может продолжиться."


def test_get_insight_detail_missing_returns_404() -> None:
    app = create_app()
    _override_detail(app, _FakeGetInsightDetail(error=InsightNotFoundError(999)))
    client = TestClient(app)

    response = client.get("/insights/999")

    assert response.status_code == 404


def test_insights_endpoints_without_database_configured_return_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same safe-503, no-SQL-detail pattern as `/watchlist` when
    `TRADING_AI_DATABASE_URL` is unset (task scope §22)."""
    monkeypatch.delenv("TRADING_AI_DATABASE_URL", raising=False)
    app = create_app()
    with TestClient(app) as client:
        save_response = client.post("/instruments/AAPL/insights", json={"analysis_token": "x"})
        list_response = client.get("/instruments/AAPL/insights")
        detail_response = client.get("/insights/1")

    assert save_response.status_code == 503
    assert list_response.status_code == 503
    assert detail_response.status_code == 503
    for response in (save_response, list_response, detail_response):
        assert "sql" not in response.text.lower()
        assert "traceback" not in response.text.lower()


def test_save_insight_response_never_contains_api_key() -> None:
    app = create_app()
    _override_save(app, _FakeSaveInsight(result=_sample_saved_insight()))
    client = TestClient(app)

    response = client.post("/instruments/AAPL/insights", json={"analysis_token": "tok-1"})

    assert _FAKE_LLM_API_KEY not in response.text
    assert "api.x.ai" not in response.text


def test_generate_then_save_full_flow_via_real_pending_cache_no_db() -> None:
    """End-to-end at the HTTP layer: the real `PendingAnalysisCache` and
    real `SaveInsight`/`ListInstrumentInsights` use cases run — only the
    generation use case and the DB-facing repository are faked. Proves
    the save endpoint only ever persists the server-held analysis, never
    anything the client could have supplied (task scope §12)."""
    app = create_app()
    analysis = _sample_analysis()
    app.dependency_overrides[get_generate_instrument_analysis_use_case] = (
        lambda: _FakeGenerateInstrumentAnalysis(analysis)
    )
    fake_repository = _FakeInsightRepository()
    app.dependency_overrides[get_insight_repository] = lambda: fake_repository
    client = TestClient(app)

    generate_response = client.post("/instruments/AAPL/analysis")
    assert generate_response.status_code == 200
    token = generate_response.json()["analysis_token"]

    save_response = client.post("/instruments/AAPL/insights", json={"analysis_token": token})
    assert save_response.status_code == 201
    saved_body = save_response.json()
    assert saved_body["summary"] == analysis.summary
    assert saved_body["provider"] == "xai"
    assert len(fake_repository.added) == 1
    assert fake_repository.added[0].summary == analysis.summary

    history_response = client.get("/instruments/AAPL/insights")
    assert history_response.status_code == 200
    assert len(history_response.json()["items"]) == 1

    # The same token cannot be saved twice.
    second_save_response = client.post("/instruments/AAPL/insights", json={"analysis_token": token})
    assert second_save_response.status_code == 404
    assert len(fake_repository.added) == 1
