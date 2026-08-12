"""Opt-in integration tests for news-intelligence persistence against real
PostgreSQL (task scope §17, §20). Mirrors `test_insights_integration.py`.

    TRADING_AI_TEST_DATABASE_URL=postgresql+asyncpg://user:pass@host:port/db \\
        python -m pytest -m integration tests/integration

Assumes the Alembic migration chain (through `0006_news_intelligence_items`)
has already been applied. Each test uses a randomly generated ticker and
deletes its own rows afterward in a `finally`.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from trading_ai.ai.types import NewsRelationship, NewsRelevance
from trading_ai.news_intelligence.domain import NewNewsIntelligenceRow, PersistedNewsIntelligenceItem

pytestmark = pytest.mark.integration

_TEST_DATABASE_URL = os.environ.get("TRADING_AI_TEST_DATABASE_URL")
_SKIP_REASON = (
    "TRADING_AI_TEST_DATABASE_URL is not set - skipping real "
    "PostgreSQL integration test (opt-in only)."
)

_T = datetime(2026, 8, 10, 15, 0, 0, tzinfo=timezone.utc)


def _unique_ticker() -> str:
    return "ZNEWS" + uuid.uuid4().hex[:6].upper()


def _new_row(ticker: str, provider_news_id: str, **overrides: object) -> NewNewsIntelligenceRow:
    fields: dict[str, object] = {
        "ticker": ticker,
        "news_provider": "finnhub",
        "provider_news_id": provider_news_id,
        "headline_original": "Test headline",
        "source": "Reuters",
        "published_at": _T,
        "url": "https://example.com/a",
        "enriched": True,
        "summary_ru": "Тестовое резюме.",
        "why_it_matters": "Тестовое объяснение важности.",
        "relevance": NewsRelevance.HIGH,
        "relationship": NewsRelationship.COMPANY,
        "impact_hypothesis": "Тестовая гипотеза влияния.",
        "llm_provider": "xai",
        "llm_model": "grok-4.5",
        "llm_prompt_version": "news-intelligence-v1",
        "llm_schema_version": "news-intelligence-v1",
    }
    fields.update(overrides)
    return NewNewsIntelligenceRow(**fields)  # type: ignore[arg-type]


def _delete_ticker(ticker: str) -> None:
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None

    async def _run() -> None:
        from trading_ai.infrastructure.database.engine import create_database_engine

        engine = create_database_engine(test_database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM news_intelligence_items WHERE ticker = :ticker"),
                    {"ticker": ticker},
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_add_and_get_existing_round_trips_all_fields() -> None:
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None
    ticker = _unique_ticker()

    async def _run() -> None:
        from trading_ai.infrastructure.database.engine import create_database_engine
        from trading_ai.infrastructure.database.session import create_session_factory, session_scope
        from trading_ai.news_intelligence.repository import NewsIntelligenceRepository

        engine = create_database_engine(test_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as session:
                repository = NewsIntelligenceRepository(session)
                saved = await repository.add(_new_row(ticker, "news-1"))

            async with session_scope(factory) as session:
                repository = NewsIntelligenceRepository(session)
                existing = await repository.get_existing_for_ticker(ticker, "finnhub", ["news-1"])

            assert saved.ticker == ticker
            assert saved.summary_ru == "Тестовое резюме."
            assert saved.relevance == NewsRelevance.HIGH
            assert saved.relationship == NewsRelationship.COMPANY
            assert "news-1" in existing
            assert existing["news-1"].id == saved.id
            assert existing["news-1"].created_at.tzinfo is not None
        finally:
            await engine.dispose()

    try:
        asyncio.run(_run())
    finally:
        _delete_ticker(ticker)


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_get_existing_for_ticker_only_returns_requested_ids() -> None:
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None
    ticker = _unique_ticker()

    async def _run() -> dict[str, PersistedNewsIntelligenceItem]:
        from trading_ai.infrastructure.database.engine import create_database_engine
        from trading_ai.infrastructure.database.session import create_session_factory, session_scope
        from trading_ai.news_intelligence.repository import NewsIntelligenceRepository

        engine = create_database_engine(test_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as session:
                repository = NewsIntelligenceRepository(session)
                await repository.add(_new_row(ticker, "news-1"))
                await repository.add(_new_row(ticker, "news-2"))

            async with session_scope(factory) as session:
                repository = NewsIntelligenceRepository(session)
                existing = await repository.get_existing_for_ticker(ticker, "finnhub", ["news-1"])
            return existing
        finally:
            await engine.dispose()

    try:
        existing = asyncio.run(_run())
        assert set(existing.keys()) == {"news-1"}
    finally:
        _delete_ticker(ticker)


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_get_existing_for_ticker_empty_ids_returns_empty_without_query() -> None:
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None

    async def _run() -> dict[str, PersistedNewsIntelligenceItem]:
        from trading_ai.infrastructure.database.engine import create_database_engine
        from trading_ai.infrastructure.database.session import create_session_factory, session_scope
        from trading_ai.news_intelligence.repository import NewsIntelligenceRepository

        engine = create_database_engine(test_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as session:
                repository = NewsIntelligenceRepository(session)
                return await repository.get_existing_for_ticker("NOPE", "finnhub", [])
        finally:
            await engine.dispose()

    assert asyncio.run(_run()) == {}


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_unique_constraint_prevents_duplicate_ticker_provider_item() -> None:
    """Same `(ticker, news_provider, provider_news_id)` twice must
    violate the unique constraint — this is what makes the table a
    correct reuse cache (task scope §10), not just a log."""
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None
    ticker = _unique_ticker()

    async def _run() -> None:
        from sqlalchemy.exc import IntegrityError

        from trading_ai.infrastructure.database.engine import create_database_engine
        from trading_ai.infrastructure.database.session import create_session_factory, session_scope
        from trading_ai.news_intelligence.repository import NewsIntelligenceRepository

        engine = create_database_engine(test_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as session:
                repository = NewsIntelligenceRepository(session)
                await repository.add(_new_row(ticker, "news-dup"))

            with pytest.raises(IntegrityError):
                async with session_scope(factory) as session:
                    repository = NewsIntelligenceRepository(session)
                    await repository.add(_new_row(ticker, "news-dup"))
        finally:
            await engine.dispose()

    try:
        asyncio.run(_run())
    finally:
        _delete_ticker(ticker)


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_repository_has_no_update_or_delete_method() -> None:
    """Structural immutability check (ADR-0004 §20, same pattern as
    `insights`/`journal`): only insert and read are exposed."""
    from trading_ai.news_intelligence.repository import NewsIntelligenceRepository

    assert not hasattr(NewsIntelligenceRepository, "update")
    assert not hasattr(NewsIntelligenceRepository, "delete")
