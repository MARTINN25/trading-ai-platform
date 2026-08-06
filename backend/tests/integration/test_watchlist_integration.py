"""Opt-in integration tests for the watchlist vertical slice.

Skipped by default — mirrors `test_database_integration.py`. To run:

    TRADING_AI_TEST_DATABASE_URL=postgresql+asyncpg://user:pass@host:port/db \\
        python -m pytest -m integration tests/integration

Assumes the Alembic migration chain (through `0002_watchlist_items`)
has already been applied to the target database — this test does not
run migrations and does not create schema. Always PostgreSQL, never
SQLite. Each test uses a randomly generated ticker and deletes it
afterward, so the shared local development database is left clean and
tests do not collide with each other or with pre-existing data.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

pytestmark = pytest.mark.integration

_TEST_DATABASE_URL = os.environ.get("TRADING_AI_TEST_DATABASE_URL")
_SKIP_REASON = (
    "TRADING_AI_TEST_DATABASE_URL is not set - skipping real "
    "PostgreSQL integration test (opt-in only)."
)


def _unique_ticker() -> str:
    """A short ticker unlikely to collide with any other test run."""
    return "ZTEST" + uuid.uuid4().hex[:6].upper()


def _delete_ticker(ticker: str) -> None:
    """Best-effort cleanup, run regardless of test outcome."""
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None

    async def _run() -> None:
        from trading_ai.infrastructure.database.engine import create_database_engine

        engine = create_database_engine(test_database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM watchlist_items WHERE ticker = :ticker"),
                    {"ticker": ticker},
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


@pytest.fixture
def watchlist_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None
    monkeypatch.setenv("TRADING_AI_DATABASE_URL", test_database_url)

    from trading_ai.main import create_app

    app = create_app()
    with TestClient(app) as client:
        yield client


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_post_creates_a_real_row_and_get_returns_it(
    watchlist_client: TestClient,
) -> None:
    ticker = _unique_ticker()
    try:
        post_response = watchlist_client.post("/watchlist", json={"ticker": ticker})
        assert post_response.status_code == 201
        body = post_response.json()
        assert body["ticker"] == ticker
        assert body["id"] is not None
        assert body["created_at"] is not None

        get_response = watchlist_client.get("/watchlist")
        assert get_response.status_code == 200
        tickers = [item["ticker"] for item in get_response.json()]
        assert ticker in tickers
    finally:
        _delete_ticker(ticker)


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_duplicate_post_returns_409_against_real_unique_constraint(
    watchlist_client: TestClient,
) -> None:
    ticker = _unique_ticker()
    try:
        first = watchlist_client.post("/watchlist", json={"ticker": ticker})
        assert first.status_code == 201

        second = watchlist_client.post("/watchlist", json={"ticker": ticker})
        assert second.status_code == 409

        get_response = watchlist_client.get("/watchlist")
        matching = [item["ticker"] for item in get_response.json() if item["ticker"] == ticker]
        assert len(matching) == 1
    finally:
        _delete_ticker(ticker)


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_duplicate_post_with_different_case_is_still_rejected(
    watchlist_client: TestClient,
) -> None:
    ticker = _unique_ticker()
    try:
        first = watchlist_client.post("/watchlist", json={"ticker": ticker.lower()})
        assert first.status_code == 201

        second = watchlist_client.post("/watchlist", json={"ticker": ticker.upper()})
        assert second.status_code == 409
    finally:
        _delete_ticker(ticker)


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason=_SKIP_REASON)
def test_list_all_breaks_created_at_ties_by_id() -> None:
    """`created_at` alone can repeat (server `now()` has finite resolution
    and can coincide within one transaction) — `list_all()` must still
    return a deterministic order, falling back to `id` ascending.

    Inserted directly through `WatchlistRepository` with an identical,
    explicit `created_at` for both rows, and in an order (second ticker
    first) that would fail this test if the tie-break were missing or
    accidentally relied on insertion/ticker order instead of `id`.
    """
    test_database_url = _TEST_DATABASE_URL
    assert test_database_url is not None

    ticker_lower_id = _unique_ticker()
    ticker_higher_id = _unique_ticker()

    async def _run() -> list[str]:
        from trading_ai.infrastructure.database.engine import create_database_engine
        from trading_ai.infrastructure.database.session import (
            create_session_factory,
            session_scope,
        )
        from trading_ai.watchlist.repository import WatchlistRepository

        engine = create_database_engine(test_database_url)
        factory = create_session_factory(engine)
        tied_created_at = datetime.now(timezone.utc)
        try:
            async with session_scope(factory) as session:
                repository = WatchlistRepository(session)
                # Insert `ticker_lower_id` first so it gets the lower id,
                # then `ticker_higher_id` — but give both the exact same
                # `created_at` by writing it through the ORM model
                # directly (bypassing the server-side default), so the
                # test doesn't depend on clock resolution.
                from trading_ai.watchlist.models import WatchlistItemModel

                first_model = WatchlistItemModel(
                    ticker=ticker_lower_id, created_at=tied_created_at
                )
                session.add(first_model)
                await session.flush()

                second_model = WatchlistItemModel(
                    ticker=ticker_higher_id, created_at=tied_created_at
                )
                session.add(second_model)
                await session.flush()

                assert first_model.created_at == second_model.created_at
                assert first_model.id < second_model.id

                items = await repository.list_all()
            return [item.ticker for item in items]
        finally:
            await engine.dispose()

    try:
        tickers = asyncio.run(_run())
        our_tickers = [t for t in tickers if t in (ticker_lower_id, ticker_higher_id)]
        assert our_tickers == [ticker_lower_id, ticker_higher_id]
    finally:
        _delete_ticker(ticker_lower_id)
        _delete_ticker(ticker_higher_id)
