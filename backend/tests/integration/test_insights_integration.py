"""Opt-in integration tests for insight persistence against real
PostgreSQL (task scope §20). Mirrors `test_watchlist_integration.py`.

    TRADING_AI_TEST_DATABASE_URL=postgresql+asyncpg://user:pass@host:port/db \\
        python -m pytest -m integration tests/integration

Assumes the Alembic migration chain (through `0003_insights`) has
already been applied. Each test uses a randomly generated ticker and
deletes its own rows afterward in a `finally`, so the shared local
database is left clean.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from trading_ai.ai.types import ConfidenceLevel, KeyFact
from trading_ai.insights.domain import NewInsight

pytestmark = pytest.mark.integration

_TEST_DATABASE_URL = os.environ.get("TRADING_AI_TEST_DATABASE_URL")
_SKIP_REASON = (
    "TRADING_AI_TEST_DATABASE_URL is not set - skipping real "
    "PostgreSQL integration test (opt-in only)."
)

_T = datetime(2026, 3, 2, 14, 30, tzinfo=timezone.utc)


def _unique_ticker() -> str:
    return "ZTEST" + uuid.uuid4().hex[:6].upper()


def _new_insight(ticker: str, **overrides: object) -> NewInsight:
    fields: dict[str, object] = {
        "ticker": ticker,
        "generated_at": _T,
        "summary": "Тестовое резюме.",
        "price_context": "Тестовый контекст цены.",
        "news_context": "Тестовый контекст новостей.",
        "key_facts": (KeyFact(fact="Тестовый факт.", source="Текущая котировка"),),
        "insight_hypothesis": "Тестовая гипотеза.",
        "confidence": ConfidenceLevel.MEDIUM,
        "confidence_reason": "Тестовое обоснование уверенности.",
        "considerations": ("Тестовое соображение.",),
        "risks": ("Тестовый риск.",),
        "key_drivers": ("Тестовый ключевой фактор.",),
        "data_freshness": "Тестовая актуальность данных.",
        "source_data_as_of": _T,
        "disclaimer": "AI-анализ носит информационный характер и не является инвестиционной рекомендацией.",
        "provider": "xai",
        "model": "grok-4.5",
        "prompt_version": "instrument-analysis-v2",
        "schema_version": "insight-structure-v1",
    }
    fields.update(overrides)
    return NewInsight(**fields)  # type: ignore[arg-type]


def _delete_ticker(ticker: str) -> None:
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None

    async def _run() -> None:
        from trading_ai.infrastructure.database.engine import create_database_engine

        engine = create_database_engine(test_database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM insights WHERE ticker = :ticker"), {"ticker": ticker}
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_add_and_get_by_id_round_trips_all_fields() -> None:
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None
    ticker = _unique_ticker()

    async def _run() -> None:
        from trading_ai.infrastructure.database.engine import create_database_engine
        from trading_ai.infrastructure.database.session import create_session_factory, session_scope
        from trading_ai.insights.repository import InsightRepository

        engine = create_database_engine(test_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as session:
                repository = InsightRepository(session)
                saved = await repository.add(_new_insight(ticker))
                fetched = await repository.get_by_id(saved.id)

            assert fetched is not None
            assert fetched.ticker == ticker
            assert fetched.summary == "Тестовое резюме."
            assert fetched.key_facts == (KeyFact(fact="Тестовый факт.", source="Текущая котировка"),)
            assert fetched.confidence == ConfidenceLevel.MEDIUM
            assert fetched.confidence_reason == "Тестовое обоснование уверенности."
            assert fetched.considerations == ("Тестовое соображение.",)
            assert fetched.risks == ("Тестовый риск.",)
            assert fetched.key_drivers == ("Тестовый ключевой фактор.",)
            assert fetched.data_freshness == "Тестовая актуальность данных."
            assert fetched.source_data_as_of == _T
            assert fetched.provider == "xai"
            assert fetched.model == "grok-4.5"
            assert fetched.prompt_version == "instrument-analysis-v2"
            assert fetched.schema_version == "insight-structure-v1"
            assert fetched.generated_at.tzinfo is not None
            assert fetched.created_at.tzinfo is not None
            # Phase 2B (migration 0007): a legacy-shaped insert (no
            # forecast kwargs given) round-trips with every new column
            # NULL -> None, never a fabricated default.
            assert fetched.horizon is None
            assert fetched.forecast_state is None
            assert fetched.directional_view is None
            assert fetched.concise_verdict is None
            assert fetched.catalysts == ()
            assert fetched.check_after is None
        finally:
            await engine.dispose()

    try:
        asyncio.run(_run())
    finally:
        _delete_ticker(ticker)


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_add_and_get_by_id_round_trips_forecast_fields() -> None:
    """Phase 2B (migration 0007) — a forecast-bearing insight round-trips
    through real PostgreSQL exactly like the legacy-shaped one above,
    proving the additive columns actually persist and read back
    correctly, not just that they exist in the schema."""
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None
    ticker = _unique_ticker()

    async def _run() -> None:
        from trading_ai.ai.types import AnalysisHorizon, DirectionalView, ForecastState
        from trading_ai.infrastructure.database.engine import create_database_engine
        from trading_ai.infrastructure.database.session import create_session_factory, session_scope
        from trading_ai.insights.repository import InsightRepository

        engine = create_database_engine(test_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as session:
                repository = InsightRepository(session)
                saved = await repository.add(
                    _new_insight(
                        ticker,
                        prompt_version="instrument-analysis-v3-forecast",
                        schema_version="insight-structure-v2-forecast",
                        horizon=AnalysisHorizon.LONG,
                        forecast_state=ForecastState.FORECAST,
                        directional_view=DirectionalView.STRONGLY_BULLISH,
                        concise_verdict="Тестовый вывод.",
                        base_case="Тестовый базовый сценарий.",
                        bullish_case="Тестовый бычий сценарий.",
                        bearish_case="Тестовый медвежий сценарий.",
                        catalysts=("Тестовый катализатор.",),
                        invalidation_conditions=("Тестовое условие инвалидации.",),
                        what_to_watch_next=("Тестовое что отслеживать.",),
                        check_after=_T,
                        uncertainty="Тестовая неопределённость.",
                        context_categories_used=("identity", "price", "history"),
                    )
                )
                fetched = await repository.get_by_id(saved.id)

            assert fetched is not None
            assert fetched.horizon == AnalysisHorizon.LONG
            assert fetched.forecast_state == ForecastState.FORECAST
            assert fetched.directional_view == DirectionalView.STRONGLY_BULLISH
            assert fetched.concise_verdict == "Тестовый вывод."
            assert fetched.catalysts == ("Тестовый катализатор.",)
            assert fetched.invalidation_conditions == ("Тестовое условие инвалидации.",)
            assert fetched.what_to_watch_next == ("Тестовое что отслеживать.",)
            assert fetched.check_after == _T
            assert fetched.uncertainty == "Тестовая неопределённость."
            assert fetched.context_categories_used == ("identity", "price", "history")
        finally:
            await engine.dispose()

    try:
        asyncio.run(_run())
    finally:
        _delete_ticker(ticker)


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_get_by_id_missing_returns_none() -> None:
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None

    async def _run() -> None:
        from trading_ai.infrastructure.database.engine import create_database_engine
        from trading_ai.infrastructure.database.session import create_session_factory, session_scope
        from trading_ai.insights.repository import InsightRepository

        engine = create_database_engine(test_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as session:
                repository = InsightRepository(session)
                result = await repository.get_by_id(2_147_483_647)
            assert result is None
        finally:
            await engine.dispose()

    asyncio.run(_run())


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_list_recent_for_ticker_is_newest_first_and_ties_broken_by_id() -> None:
    """Mirrors `test_watchlist_integration.py`'s tie-break test — two
    rows inserted with an identical, explicit `created_at` must still
    come back in a deterministic order (newest by `id` as the tiebreak,
    matching `InsightRepository.list_recent_for_ticker`'s `ORDER BY
    created_at DESC, id DESC`)."""
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None
    ticker = _unique_ticker()

    async def _run() -> list[int]:
        from trading_ai.infrastructure.database.engine import create_database_engine
        from trading_ai.infrastructure.database.session import create_session_factory, session_scope
        from trading_ai.insights.repository import InsightRepository

        engine = create_database_engine(test_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as session:
                repository = InsightRepository(session)
                first = await repository.add(_new_insight(ticker))
                second = await repository.add(_new_insight(ticker))

            # Force an identical created_at directly through the ORM so
            # the test doesn't depend on clock resolution.
            from trading_ai.insights.models import InsightModel
            from sqlalchemy import update

            async with session_scope(factory) as session:
                tied = datetime.now(timezone.utc)
                await session.execute(
                    update(InsightModel)
                    .where(InsightModel.id.in_([first.id, second.id]))
                    .values(created_at=tied)
                )

            async with session_scope(factory) as session:
                repository = InsightRepository(session)
                results = await repository.list_recent_for_ticker(ticker)
            return [item.id for item in results]
        finally:
            await engine.dispose()

    try:
        ids = asyncio.run(_run())
        # Newest-first with an id tiebreak means the higher id comes first.
        assert ids == sorted(ids, reverse=True)
        assert len(ids) == 2
    finally:
        _delete_ticker(ticker)


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_repeated_saves_for_same_ticker_create_independent_rows() -> None:
    """Two "generations" for the same ticker must both persist as
    distinct rows — insights are never overwritten (ADR-0004 §20)."""
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None
    ticker = _unique_ticker()

    async def _run() -> tuple[int, int]:
        from trading_ai.infrastructure.database.engine import create_database_engine
        from trading_ai.infrastructure.database.session import create_session_factory, session_scope
        from trading_ai.insights.repository import InsightRepository

        engine = create_database_engine(test_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as session:
                repository = InsightRepository(session)
                first = await repository.add(_new_insight(ticker, summary="Первое резюме."))
                second = await repository.add(_new_insight(ticker, summary="Второе резюме."))

            async with session_scope(factory) as session:
                repository = InsightRepository(session)
                results = await repository.list_recent_for_ticker(ticker)
            assert len(results) == 2
            summaries = {item.summary for item in results}
            assert summaries == {"Первое резюме.", "Второе резюме."}
            return first.id, second.id
        finally:
            await engine.dispose()

    try:
        first_id, second_id = asyncio.run(_run())
        assert first_id != second_id
    finally:
        _delete_ticker(ticker)


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_list_recent_is_newest_first_across_tickers_and_bounded() -> None:
    """`list_recent` (Phase 1, Insights/History area) mirrors
    `list_recent_for_ticker`'s ordering but with no ticker filter — two
    different tickers must both appear, newest-first, and a `limit`
    smaller than the total row count must actually bound the result."""
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None
    ticker_a = _unique_ticker()
    ticker_b = _unique_ticker()

    async def _run() -> list[tuple[int, str]]:
        from trading_ai.infrastructure.database.engine import create_database_engine
        from trading_ai.infrastructure.database.session import create_session_factory, session_scope
        from trading_ai.insights.repository import InsightRepository

        engine = create_database_engine(test_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as session:
                repository = InsightRepository(session)
                first = await repository.add(_new_insight(ticker_a))
                second = await repository.add(_new_insight(ticker_b))
                third = await repository.add(_new_insight(ticker_a))

            async with session_scope(factory) as session:
                repository = InsightRepository(session)
                unbounded = await repository.list_recent(limit=50)
                bounded = await repository.list_recent(limit=2)

            relevant_ids = {first.id, second.id, third.id}
            unbounded_relevant = [item for item in unbounded if item.id in relevant_ids]
            assert [item.id for item in unbounded_relevant] == [third.id, second.id, first.id]
            assert len(bounded) == 2
            return [(item.id, item.ticker) for item in bounded]
        finally:
            await engine.dispose()

    try:
        bounded_result = asyncio.run(_run())
        # The two newest rows overall must come first, regardless of
        # which ticker they belong to (task scope §8: cross-ticker).
        assert len(bounded_result) == 2
    finally:
        _delete_ticker(ticker_a)
        _delete_ticker(ticker_b)


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_repository_has_no_update_method() -> None:
    """Structural immutability check (ADR-0004 §20, task scope §7): the
    repository exposes no way to modify an existing row, only insert
    and read."""
    from trading_ai.insights.repository import InsightRepository

    assert not hasattr(InsightRepository, "update")
    assert not hasattr(InsightRepository, "delete")
