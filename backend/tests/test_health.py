from __future__ import annotations

from fastapi.testclient import TestClient

from trading_ai.main import create_app


def test_health_returns_ok() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
