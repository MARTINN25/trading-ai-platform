from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from trading_ai.main import create_app


def test_health_returns_ok() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_returns_ok_without_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Liveness must never depend on database configuration (ADR-0009, §41)."""
    monkeypatch.delenv("TRADING_AI_DATABASE_URL", raising=False)

    app = create_app()
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_app_succeeds_without_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The application (and thus `from trading_ai.main import app`) must be
    constructible without TRADING_AI_DATABASE_URL set."""
    monkeypatch.delenv("TRADING_AI_DATABASE_URL", raising=False)

    app = create_app()

    assert app.title == "AI Trading Assistant Platform"
