"""API-boundary tests for trade journal endpoints (task scope §19).
Overrides use cases directly — no httpx/asyncpg."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from trading_ai.api.routes.journal import (
    get_create_journal_entry_use_case,
    get_journal_entry_use_case,
    get_list_journal_entries_use_case,
    get_update_journal_entry_use_case,
)
from trading_ai.insights.domain import InsightNotFoundError
from trading_ai.journal.domain import (
    InvalidJournalEntryError,
    JournalEntry,
    JournalEntryNotFoundError,
    TradeDirection,
    TradeResultStatus,
)
from trading_ai.main import create_app
from trading_ai.watchlist.domain import InvalidTickerError

_T = datetime(2026, 3, 2, 14, 30, tzinfo=timezone.utc)


def _entry(
    entry_id: int = 1,
    ticker: str = "AAPL",
    insight_id: int | None = None,
    result_note: str | None = None,
    updated_at: datetime | None = None,
) -> JournalEntry:
    return JournalEntry(
        id=entry_id,
        ticker=ticker,
        direction=TradeDirection.LONG,
        result_status=TradeResultStatus.OPEN,
        result_note=result_note,
        insight_id=insight_id,
        created_at=_T,
        updated_at=updated_at,
    )


class _FakeCreateJournalEntry:
    def __init__(self, result: JournalEntry | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.received: tuple[str, TradeDirection, TradeResultStatus, str | None, int | None] | None = None

    async def execute(self, ticker, direction, result_status, result_note, insight_id):  # type: ignore[no-untyped-def]
        self.received = (ticker, direction, result_status, result_note, insight_id)
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


class _FakeListJournalEntries:
    def __init__(self, result: list[JournalEntry]) -> None:
        self._result = result

    async def execute(self) -> list[JournalEntry]:
        return self._result


class _FakeGetJournalEntry:
    def __init__(self, result: JournalEntry | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    async def execute(self, entry_id: int) -> JournalEntry:
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


class _FakeUpdateJournalEntry:
    def __init__(self, result: JournalEntry | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    async def execute(self, entry_id, ticker, direction, result_status, result_note, insight_id):  # type: ignore[no-untyped-def]
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def _override_create(app: FastAPI, fake: _FakeCreateJournalEntry) -> None:
    app.dependency_overrides[get_create_journal_entry_use_case] = lambda: fake


def _override_list(app: FastAPI, fake: _FakeListJournalEntries) -> None:
    app.dependency_overrides[get_list_journal_entries_use_case] = lambda: fake


def _override_get(app: FastAPI, fake: _FakeGetJournalEntry) -> None:
    app.dependency_overrides[get_journal_entry_use_case] = lambda: fake


def _override_update(app: FastAPI, fake: _FakeUpdateJournalEntry) -> None:
    app.dependency_overrides[get_update_journal_entry_use_case] = lambda: fake


_VALID_BODY = {
    "ticker": "AAPL",
    "direction": "long",
    "result_status": "open",
}


def test_create_journal_entry_success() -> None:
    app = create_app()
    fake = _FakeCreateJournalEntry(result=_entry())
    _override_create(app, fake)
    client = TestClient(app)

    response = client.post("/journal", json=_VALID_BODY)

    assert response.status_code == 201
    body = response.json()
    assert body["ticker"] == "AAPL"
    assert body["direction"] == "long"
    assert body["result_status"] == "open"
    assert fake.received == ("AAPL", TradeDirection.LONG, TradeResultStatus.OPEN, None, None)


def test_create_journal_entry_with_insight_link() -> None:
    app = create_app()
    _override_create(app, _FakeCreateJournalEntry(result=_entry(insight_id=7)))
    client = TestClient(app)

    response = client.post("/journal", json={**_VALID_BODY, "insight_id": 7})

    assert response.status_code == 201
    assert response.json()["insight_id"] == 7


def test_create_journal_entry_invalid_direction_returns_422() -> None:
    app = create_app()
    _override_create(app, _FakeCreateJournalEntry(result=_entry()))
    client = TestClient(app)

    response = client.post("/journal", json={**_VALID_BODY, "direction": "sideways"})

    assert response.status_code == 422


def test_create_journal_entry_invalid_result_status_returns_422() -> None:
    app = create_app()
    _override_create(app, _FakeCreateJournalEntry(result=_entry()))
    client = TestClient(app)

    response = client.post("/journal", json={**_VALID_BODY, "result_status": "huge_win"})

    assert response.status_code == 422


def test_create_journal_entry_missing_field_returns_422() -> None:
    app = create_app()
    _override_create(app, _FakeCreateJournalEntry(result=_entry()))
    client = TestClient(app)

    response = client.post("/journal", json={"ticker": "AAPL"})

    assert response.status_code == 422


def test_create_journal_entry_invalid_ticker_returns_422() -> None:
    app = create_app()
    _override_create(app, _FakeCreateJournalEntry(error=InvalidTickerError("ticker must not be empty")))
    client = TestClient(app)

    response = client.post("/journal", json={**_VALID_BODY, "ticker": ""})

    assert response.status_code == 422


def test_create_journal_entry_unknown_insight_returns_404() -> None:
    app = create_app()
    _override_create(app, _FakeCreateJournalEntry(error=InsightNotFoundError(999)))
    client = TestClient(app)

    response = client.post("/journal", json={**_VALID_BODY, "insight_id": 999})

    assert response.status_code == 404


def test_create_journal_entry_invalid_note_returns_422() -> None:
    app = create_app()
    _override_create(app, _FakeCreateJournalEntry(error=InvalidJournalEntryError("too long")))
    client = TestClient(app)

    response = client.post("/journal", json={**_VALID_BODY, "result_note": "x"})

    assert response.status_code == 422


def test_create_journal_entry_rejects_extra_body_fields() -> None:
    """No broker/order/portfolio fields accepted (task scope §5/§26)."""
    app = create_app()
    _override_create(app, _FakeCreateJournalEntry(result=_entry()))
    client = TestClient(app)

    response = client.post(
        "/journal", json={**_VALID_BODY, "entry_price": 100, "quantity": 10, "broker": "IBKR"}
    )

    assert response.status_code == 422


def test_create_journal_entry_rejects_insight_content_fields() -> None:
    """No arbitrary insight content/provenance accepted (task scope §6)."""
    app = create_app()
    _override_create(app, _FakeCreateJournalEntry(result=_entry()))
    client = TestClient(app)

    response = client.post(
        "/journal", json={**_VALID_BODY, "summary": "fabricated", "provider": "not-xai"}
    )

    assert response.status_code == 422


def test_list_journal_entries_success() -> None:
    app = create_app()
    _override_list(app, _FakeListJournalEntries(result=[_entry()]))
    client = TestClient(app)

    response = client.get("/journal")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["ticker"] == "AAPL"


def test_list_journal_entries_empty() -> None:
    app = create_app()
    _override_list(app, _FakeListJournalEntries(result=[]))
    client = TestClient(app)

    response = client.get("/journal")

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_get_journal_entry_success() -> None:
    app = create_app()
    _override_get(app, _FakeGetJournalEntry(result=_entry()))
    client = TestClient(app)

    response = client.get("/journal/1")

    assert response.status_code == 200
    assert response.json()["id"] == 1


def test_get_journal_entry_missing_returns_404() -> None:
    app = create_app()
    _override_get(app, _FakeGetJournalEntry(error=JournalEntryNotFoundError(999)))
    client = TestClient(app)

    response = client.get("/journal/999")

    assert response.status_code == 404


def test_update_journal_entry_success() -> None:
    app = create_app()
    _override_update(app, _FakeUpdateJournalEntry(result=_entry(result_note="Обновлено.", updated_at=_T)))
    client = TestClient(app)

    response = client.put("/journal/1", json={**_VALID_BODY, "result_note": "Обновлено."})

    assert response.status_code == 200
    body = response.json()
    assert body["result_note"] == "Обновлено."
    assert body["updated_at"] is not None


def test_update_journal_entry_missing_returns_404() -> None:
    app = create_app()
    _override_update(app, _FakeUpdateJournalEntry(error=JournalEntryNotFoundError(999)))
    client = TestClient(app)

    response = client.put("/journal/999", json=_VALID_BODY)

    assert response.status_code == 404


def test_update_journal_entry_no_delete_endpoint_exists() -> None:
    """Product Owner decision: editable, no delete (task scope §15)."""
    app = create_app()
    client = TestClient(app)

    response = client.delete("/journal/1")

    assert response.status_code in (404, 405)


def test_journal_endpoints_without_database_configured_return_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TRADING_AI_DATABASE_URL", raising=False)
    app = create_app()
    with TestClient(app) as client:
        create_response = client.post("/journal", json=_VALID_BODY)
        list_response = client.get("/journal")
        detail_response = client.get("/journal/1")
        update_response = client.put("/journal/1", json=_VALID_BODY)

    assert create_response.status_code == 503
    assert list_response.status_code == 503
    assert detail_response.status_code == 503
    assert update_response.status_code == 503
    for response in (create_response, list_response, detail_response, update_response):
        assert "sql" not in response.text.lower()
        assert "traceback" not in response.text.lower()


def test_create_journal_entry_response_never_contains_secrets() -> None:
    app = create_app()
    _override_create(app, _FakeCreateJournalEntry(result=_entry()))
    client = TestClient(app)

    response = client.post("/journal", json=_VALID_BODY)

    assert "api.x.ai" not in response.text
    assert "TRADING_AI" not in response.text
