"""Opt-in integration tests for trade journal persistence against real
PostgreSQL (task scope §17). Mirrors `test_evaluations_integration.py`.

    TRADING_AI_TEST_DATABASE_URL=postgresql+asyncpg://user:pass@host:port/db \\
        python -m pytest -m integration tests/integration

Assumes the Alembic migration chain (through `0005_journal_entries`)
has already been applied. Each test creates its own rows and deletes
them in a `finally`, so the shared local database is left clean.
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
from trading_ai.journal.domain import NewJournalEntry, TradeDirection, TradeResultStatus

pytestmark = pytest.mark.integration

_TEST_DATABASE_URL = os.environ.get("TRADING_AI_TEST_DATABASE_URL")
_SKIP_REASON = (
    "TRADING_AI_TEST_DATABASE_URL is not set - skipping real "
    "PostgreSQL integration test (opt-in only)."
)

_T = datetime(2026, 3, 2, 14, 30, tzinfo=timezone.utc)


def _unique_ticker() -> str:
    return "ZTEST" + uuid.uuid4().hex[:6].upper()


def _new_entry(ticker: str, **overrides: object) -> NewJournalEntry:
    fields: dict[str, object] = {
        "ticker": ticker,
        "direction": TradeDirection.LONG,
        "result_status": TradeResultStatus.OPEN,
        "result_note": None,
        "insight_id": None,
    }
    fields.update(overrides)
    return NewJournalEntry(**fields)  # type: ignore[arg-type]


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
                    text("DELETE FROM journal_entries WHERE ticker = :ticker"), {"ticker": ticker}
                )
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
def test_add_and_get_by_id_round_trips_all_fields() -> None:
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None
    ticker = _unique_ticker()

    async def _run() -> None:
        from trading_ai.infrastructure.database.engine import create_database_engine
        from trading_ai.infrastructure.database.session import create_session_factory, session_scope
        from trading_ai.journal.repository import JournalRepository

        engine = create_database_engine(test_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as session:
                saved = await JournalRepository(session).add(
                    _new_entry(ticker, result_status=TradeResultStatus.PROFIT, result_note="Хорошая сделка.")
                )
                fetched = await JournalRepository(session).get_by_id(saved.id)

            assert fetched is not None
            assert fetched.ticker == ticker
            assert fetched.direction is TradeDirection.LONG
            assert fetched.result_status is TradeResultStatus.PROFIT
            assert fetched.result_note == "Хорошая сделка."
            assert fetched.insight_id is None
            assert fetched.created_at.tzinfo is not None
            assert fetched.updated_at is None
        finally:
            await engine.dispose()

    try:
        asyncio.run(_run())
    finally:
        _cleanup(ticker)


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_get_by_id_missing_returns_none() -> None:
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None

    async def _run() -> None:
        from trading_ai.infrastructure.database.engine import create_database_engine
        from trading_ai.infrastructure.database.session import create_session_factory, session_scope
        from trading_ai.journal.repository import JournalRepository

        engine = create_database_engine(test_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as session:
                result = await JournalRepository(session).get_by_id(2_147_483_647)
            assert result is None
        finally:
            await engine.dispose()

    asyncio.run(_run())


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_list_recent_is_newest_first() -> None:
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None
    ticker = _unique_ticker()

    async def _run() -> list[int]:
        from trading_ai.infrastructure.database.engine import create_database_engine
        from trading_ai.infrastructure.database.session import create_session_factory, session_scope
        from trading_ai.journal.models import JournalEntryModel
        from trading_ai.journal.repository import JournalRepository

        engine = create_database_engine(test_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as session:
                repository = JournalRepository(session)
                first = await repository.add(_new_entry(ticker))
                second = await repository.add(_new_entry(ticker))

            from sqlalchemy import update

            async with session_scope(factory) as session:
                tied = datetime.now(timezone.utc)
                await session.execute(
                    update(JournalEntryModel)
                    .where(JournalEntryModel.id.in_([first.id, second.id]))
                    .values(created_at=tied)
                )

            async with session_scope(factory) as session:
                results = await JournalRepository(session).list_recent()
            return [item.id for item in results if item.ticker == ticker]
        finally:
            await engine.dispose()

    try:
        ids = asyncio.run(_run())
        assert ids == sorted(ids, reverse=True)
        assert len(ids) == 2
    finally:
        _cleanup(ticker)


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_optional_insight_fk_round_trips_via_real_insight() -> None:
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None
    ticker = _unique_ticker()

    async def _run() -> None:
        from trading_ai.infrastructure.database.engine import create_database_engine
        from trading_ai.infrastructure.database.session import create_session_factory, session_scope
        from trading_ai.insights.repository import InsightRepository
        from trading_ai.journal.repository import JournalRepository

        engine = create_database_engine(test_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as session:
                saved_insight = await InsightRepository(session).add(_new_insight(ticker))

            async with session_scope(factory) as session:
                saved_entry = await JournalRepository(session).add(
                    _new_entry(ticker, insight_id=saved_insight.id)
                )

            async with session_scope(factory) as session:
                fetched = await JournalRepository(session).get_by_id(saved_entry.id)
            assert fetched is not None
            assert fetched.insight_id == saved_insight.id

            async with session_scope(factory) as session:
                insight_still_intact = await InsightRepository(session).get_by_id(saved_insight.id)
            assert insight_still_intact is not None
            assert insight_still_intact.summary == "Тестовое резюме."
        finally:
            await engine.dispose()

    try:
        asyncio.run(_run())
    finally:
        _cleanup(ticker)


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_missing_insight_fk_fails_safely() -> None:
    """FK integrity is enforced by PostgreSQL itself, not just
    application code (ADR-0004: "ограничения не запрещаются ради
    удобства")."""
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None
    ticker = _unique_ticker()

    async def _run() -> bool:
        from sqlalchemy.exc import IntegrityError

        from trading_ai.infrastructure.database.engine import create_database_engine
        from trading_ai.infrastructure.database.session import create_session_factory, session_scope
        from trading_ai.journal.repository import JournalRepository

        engine = create_database_engine(test_database_url)
        factory = create_session_factory(engine)
        try:
            raised = False
            try:
                async with session_scope(factory) as session:
                    await JournalRepository(session).add(
                        _new_entry(ticker, insight_id=2_147_483_647)
                    )
            except IntegrityError:
                raised = True
            return raised
        finally:
            await engine.dispose()

    try:
        assert asyncio.run(_run()) is True
    finally:
        _cleanup(ticker)


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_update_semantics_sets_updated_at_and_persists_changes() -> None:
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None
    ticker = _unique_ticker()

    async def _run() -> None:
        from trading_ai.evaluations.repository import EvaluationRepository
        from trading_ai.infrastructure.database.engine import create_database_engine
        from trading_ai.infrastructure.database.session import create_session_factory, session_scope
        from trading_ai.journal.domain import JournalEntryEdit
        from trading_ai.journal.repository import JournalRepository

        engine = create_database_engine(test_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as session:
                saved = await JournalRepository(session).add(_new_entry(ticker))
            assert saved.updated_at is None

            async with session_scope(factory) as session:
                updated = await JournalRepository(session).update(
                    saved.id,
                    JournalEntryEdit(
                        ticker=ticker,
                        direction=TradeDirection.SHORT,
                        result_status=TradeResultStatus.LOSS,
                        result_note="Скорректировано.",
                        insight_id=None,
                    ),
                    datetime.now(timezone.utc),
                )
            assert updated is not None
            assert updated.direction is TradeDirection.SHORT
            assert updated.result_status is TradeResultStatus.LOSS
            assert updated.result_note == "Скорректировано."
            assert updated.updated_at is not None
            assert updated.created_at == saved.created_at

            # Unrelated tables remain untouched by this update.
            async with session_scope(factory) as session:
                eval_rows = await EvaluationRepository(session).get_by_insight_id(2_147_483_647)
            assert eval_rows is None
        finally:
            await engine.dispose()

    try:
        asyncio.run(_run())
    finally:
        _cleanup(ticker)


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_update_missing_entry_returns_none() -> None:
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None

    async def _run() -> None:
        from trading_ai.infrastructure.database.engine import create_database_engine
        from trading_ai.infrastructure.database.session import create_session_factory, session_scope
        from trading_ai.journal.domain import JournalEntryEdit
        from trading_ai.journal.repository import JournalRepository

        engine = create_database_engine(test_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as session:
                result = await JournalRepository(session).update(
                    2_147_483_647,
                    JournalEntryEdit(
                        ticker="AAPL",
                        direction=TradeDirection.LONG,
                        result_status=TradeResultStatus.OPEN,
                        result_note=None,
                        insight_id=None,
                    ),
                    datetime.now(timezone.utc),
                )
            assert result is None
        finally:
            await engine.dispose()

    asyncio.run(_run())


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_repository_has_no_delete_method() -> None:
    """Structural check (Product Owner: editable, no delete)."""
    from trading_ai.journal.repository import JournalRepository

    assert not hasattr(JournalRepository, "delete")
