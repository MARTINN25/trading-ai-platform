"""API-boundary tests — no real database (`app.dependency_overrides`).

Overrides the use-case dependencies directly (not the DB session), so
these tests never touch `AsyncSession`/asyncpg at all — matching
ADR-0002 §27 criterion 12.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from trading_ai.api.routes.watchlist import (
    get_add_watchlist_item_use_case,
    get_list_watchlist_items_use_case,
    get_remove_watchlist_item_use_case,
)
from trading_ai.main import create_app
from trading_ai.watchlist.domain import (
    DuplicateTickerError,
    WatchlistItem,
    WatchlistItemNotFoundError,
)


class _FakeAddWatchlistItem:
    def __init__(self, result: WatchlistItem | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.received_ticker: str | None = None

    async def execute(self, raw_ticker: str) -> WatchlistItem:
        self.received_ticker = raw_ticker
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


class _FakeListWatchlistItems:
    def __init__(self, items: list[WatchlistItem]) -> None:
        self._items = items

    async def execute(self) -> list[WatchlistItem]:
        return self._items


class _FakeRemoveWatchlistItem:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error
        self.received_item_id: int | None = None

    async def execute(self, item_id: int) -> None:
        self.received_item_id = item_id
        if self._error is not None:
            raise self._error


def test_post_watchlist_success_returns_201_via_fake_use_case() -> None:
    app = create_app()
    fake_item = WatchlistItem(id=1, ticker="AAPL", created_at=datetime.now(timezone.utc))
    fake_use_case = _FakeAddWatchlistItem(result=fake_item)
    app.dependency_overrides[get_add_watchlist_item_use_case] = lambda: fake_use_case
    client = TestClient(app)

    response = client.post("/watchlist", json={"ticker": "aapl"})

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 1
    assert body["ticker"] == "AAPL"
    assert "created_at" in body
    assert fake_use_case.received_ticker == "aapl"


def test_post_watchlist_duplicate_returns_409() -> None:
    app = create_app()
    fake_use_case = _FakeAddWatchlistItem(error=DuplicateTickerError("AAPL"))
    app.dependency_overrides[get_add_watchlist_item_use_case] = lambda: fake_use_case
    client = TestClient(app)

    response = client.post("/watchlist", json={"ticker": "AAPL"})

    assert response.status_code == 409
    body = response.text.lower()
    assert "traceback" not in body
    assert "duplicatetickererror" not in body


def test_get_watchlist_returns_list_via_fake_use_case() -> None:
    app = create_app()
    items = [
        WatchlistItem(id=1, ticker="AAPL", created_at=datetime.now(timezone.utc)),
        WatchlistItem(id=2, ticker="MSFT", created_at=datetime.now(timezone.utc)),
    ]
    app.dependency_overrides[get_list_watchlist_items_use_case] = lambda: _FakeListWatchlistItems(
        items
    )
    client = TestClient(app)

    response = client.get("/watchlist")

    assert response.status_code == 200
    body = response.json()
    assert [entry["ticker"] for entry in body] == ["AAPL", "MSFT"]


def test_get_watchlist_returns_empty_list_when_no_items() -> None:
    app = create_app()
    app.dependency_overrides[get_list_watchlist_items_use_case] = lambda: _FakeListWatchlistItems(
        []
    )
    client = TestClient(app)

    response = client.get("/watchlist")

    assert response.status_code == 200
    assert response.json() == []


def test_delete_watchlist_item_returns_204_with_no_body() -> None:
    app = create_app()
    fake_use_case = _FakeRemoveWatchlistItem()
    app.dependency_overrides[get_remove_watchlist_item_use_case] = lambda: fake_use_case
    client = TestClient(app)

    response = client.delete("/watchlist/42")

    assert response.status_code == 204
    assert response.content == b""
    assert fake_use_case.received_item_id == 42


def test_delete_watchlist_item_missing_returns_404() -> None:
    app = create_app()
    fake_use_case = _FakeRemoveWatchlistItem(error=WatchlistItemNotFoundError(999))
    app.dependency_overrides[get_remove_watchlist_item_use_case] = lambda: fake_use_case
    client = TestClient(app)

    response = client.delete("/watchlist/999")

    assert response.status_code == 404
    body = response.text.lower()
    assert "traceback" not in body
    assert "watchlistitemnotfounderror" not in body


def test_delete_watchlist_item_invalid_id_returns_422() -> None:
    # Overrides the use-case dependency (not because it should ever run
    # here — path validation must reject "not-a-number" before the
    # handler body executes) so this test isolates FastAPI's own path
    # validation instead of tripping the unrelated "database not
    # configured" 503 from the real, unoverridden dependency chain.
    app = create_app()
    fake_use_case = _FakeRemoveWatchlistItem()
    app.dependency_overrides[get_remove_watchlist_item_use_case] = lambda: fake_use_case
    client = TestClient(app)

    response = client.delete("/watchlist/not-a-number")

    assert response.status_code == 422
    assert fake_use_case.received_item_id is None


def test_post_watchlist_without_database_configured_returns_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TRADING_AI_DATABASE_URL", raising=False)
    app = create_app()
    with TestClient(app) as client:
        response = client.post("/watchlist", json={"ticker": "AAPL"})

    assert response.status_code == 503
