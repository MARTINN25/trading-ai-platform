from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from trading_ai.api.routes.ready import get_readiness_status
from trading_ai.main import create_app


def test_ready_returns_ok_when_database_check_succeeds() -> None:
    app = create_app()
    app.dependency_overrides[get_readiness_status] = lambda: True
    client = TestClient(app)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_unavailable_when_database_check_fails() -> None:
    app = create_app()
    app.dependency_overrides[get_readiness_status] = lambda: False
    client = TestClient(app)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


def test_ready_returns_unavailable_without_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No TRADING_AI_DATABASE_URL -> no engine -> controlled 503, not a crash."""
    monkeypatch.delenv("TRADING_AI_DATABASE_URL", raising=False)

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}

    body = response.text.lower()
    assert "postgresql" not in body
    assert "asyncpg" not in body
    assert "password" not in body
    assert "traceback" not in body


def test_ready_unavailable_response_does_not_leak_database_details() -> None:
    app = create_app()
    app.dependency_overrides[get_readiness_status] = lambda: False
    client = TestClient(app)

    response = client.get("/ready")

    body = response.text.lower()
    assert "postgresql" not in body
    assert "asyncpg" not in body
    assert "trading_ai_test" not in body
    assert "@localhost" not in body
    assert "password" not in body
    assert "traceback" not in body
