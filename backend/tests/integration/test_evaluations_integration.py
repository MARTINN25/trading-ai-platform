"""Opt-in integration tests for insight evaluation/outcome persistence
against real PostgreSQL (task scope §20). Mirrors
`test_insights_integration.py`.

    TRADING_AI_TEST_DATABASE_URL=postgresql+asyncpg://user:pass@host:port/db \\
        python -m pytest -m integration tests/integration

Assumes the Alembic migration chain (through `0004_insight_evaluations`)
has already been applied. Each test creates its own insight row (via
`InsightRepository`, a real FK target) and deletes both it and any
evaluation row in a `finally`, so the shared local database is left clean.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from trading_ai.ai.types import ConfidenceLevel, KeyFact
from trading_ai.evaluations.domain import InsightRating
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


def _new_insight(ticker: str) -> NewInsight:
    return NewInsight(
        ticker=ticker,
        generated_at=_T,
        summary="Тестовое резюме.",
        price_context="Тестовый контекст цены.",
        news_context="Тестовый контекст новостей.",
        key_facts=(KeyFact(fact="Тестовый факт.", source="Текущая котировка"),),
        insight_hypothesis="Тестовая гипотеза.",
        confidence=ConfidenceLevel.MEDIUM,
        confidence_reason="Тестовое обоснование уверенности.",
        considerations=("Тестовое соображение.",),
        risks=("Тестовый риск.",),
        key_drivers=("Тестовый ключевой фактор.",),
        data_freshness="Тестовая актуальность данных.",
        source_data_as_of=_T,
        disclaimer="AI-анализ носит информационный характер и не является инвестиционной рекомендацией.",
        provider="xai",
        model="grok-4.5",
        prompt_version="instrument-analysis-v2",
        schema_version="insight-structure-v1",
    )


def _cleanup(ticker: str) -> None:
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None

    async def _run() -> None:
        from trading_ai.infrastructure.database.engine import create_database_engine

        engine = create_database_engine(test_database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "DELETE FROM insight_evaluations WHERE insight_id IN "
                        "(SELECT id FROM insights WHERE ticker = :ticker)"
                    ),
                    {"ticker": ticker},
                )
                await connection.execute(
                    text("DELETE FROM insights WHERE ticker = :ticker"), {"ticker": ticker}
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_evaluate_then_read_round_trips_via_real_insight_fk() -> None:
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None
    ticker = _unique_ticker()

    async def _run() -> None:
        from trading_ai.evaluations.repository import EvaluationRepository
        from trading_ai.infrastructure.database.engine import create_database_engine
        from trading_ai.infrastructure.database.session import create_session_factory, session_scope
        from trading_ai.insights.repository import InsightRepository

        engine = create_database_engine(test_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as session:
                saved_insight = await InsightRepository(session).add(_new_insight(ticker))

            async with session_scope(factory) as session:
                await EvaluationRepository(session).upsert_rating(
                    saved_insight.id, InsightRating.USEFUL, _T
                )

            async with session_scope(factory) as session:
                fetched = await EvaluationRepository(session).get_by_insight_id(saved_insight.id)

            assert fetched is not None
            assert fetched.insight_id == saved_insight.id
            assert fetched.rating is InsightRating.USEFUL
            assert fetched.rated_at is not None
            assert fetched.outcome_note is None
        finally:
            await engine.dispose()

    try:
        asyncio.run(_run())
    finally:
        _cleanup(ticker)


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_get_by_insight_id_missing_returns_none() -> None:
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None

    async def _run() -> None:
        from trading_ai.evaluations.repository import EvaluationRepository
        from trading_ai.infrastructure.database.engine import create_database_engine
        from trading_ai.infrastructure.database.session import create_session_factory, session_scope

        engine = create_database_engine(test_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as session:
                result = await EvaluationRepository(session).get_by_insight_id(2_147_483_647)
            assert result is None
        finally:
            await engine.dispose()

    asyncio.run(_run())


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_foreign_key_rejects_unknown_insight_id() -> None:
    """FK integrity is enforced by PostgreSQL itself, not just application
    code (ADR-0004: "ограничения не запрещаются ради удобства")."""
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None

    async def _run() -> bool:
        from sqlalchemy.exc import IntegrityError

        from trading_ai.evaluations.repository import EvaluationRepository
        from trading_ai.infrastructure.database.engine import create_database_engine
        from trading_ai.infrastructure.database.session import create_session_factory, session_scope

        engine = create_database_engine(test_database_url)
        factory = create_session_factory(engine)
        try:
            raised = False
            try:
                async with session_scope(factory) as session:
                    await EvaluationRepository(session).upsert_rating(
                        2_147_483_647, InsightRating.USEFUL, _T
                    )
            except IntegrityError:
                raised = True
            return raised
        finally:
            await engine.dispose()

    assert asyncio.run(_run()) is True


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_outcome_can_be_recorded_independently_and_updates_same_row() -> None:
    """One evaluation record per insight (unique constraint) — outcome
    set after rating updates the same row, does not create a second one."""
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None
    ticker = _unique_ticker()

    async def _run() -> None:
        from trading_ai.evaluations.repository import EvaluationRepository
        from trading_ai.infrastructure.database.engine import create_database_engine
        from trading_ai.infrastructure.database.session import create_session_factory, session_scope
        from trading_ai.insights.repository import InsightRepository

        engine = create_database_engine(test_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as session:
                saved_insight = await InsightRepository(session).add(_new_insight(ticker))

            async with session_scope(factory) as session:
                first = await EvaluationRepository(session).upsert_rating(
                    saved_insight.id, InsightRating.USEFUL, _T
                )

            async with session_scope(factory) as session:
                second = await EvaluationRepository(session).upsert_outcome(
                    saved_insight.id, "Подтвердилось на практике.", _T
                )

            assert first.id == second.id
            assert second.rating is InsightRating.USEFUL
            assert second.outcome_note == "Подтвердилось на практике."
            assert second.updated_at is not None

            async with session_scope(factory) as session:
                fetched_insight = await InsightRepository(session).get_by_id(saved_insight.id)
            assert fetched_insight is not None
            assert fetched_insight.summary == "Тестовое резюме."
        finally:
            await engine.dispose()

    try:
        asyncio.run(_run())
    finally:
        _cleanup(ticker)


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_repository_has_no_delete_method() -> None:
    """Structural check (task scope §6): no delete architecture was
    introduced — only get/upsert exist."""
    from trading_ai.evaluations.repository import EvaluationRepository

    assert not hasattr(EvaluationRepository, "delete")
