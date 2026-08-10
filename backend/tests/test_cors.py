"""CORS allowlist tests for the config-driven policy in `main.py`.

Origins come from `Settings.cors_origins` (`TRADING_AI_CORS_ORIGINS`,
parsed centrally in `config.py`), defaulting to the two local Next.js
dev origins when unset. These tests verify: the dev-default origins
are allowed, credentials are not enabled, an arbitrary origin is not
reflected back, and a custom `TRADING_AI_CORS_ORIGINS` actually
replaces the default — without exercising a real database.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from trading_ai.main import create_app


def test_allowed_dev_origin_gets_cors_headers_on_get(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TRADING_AI_CORS_ORIGINS", raising=False)
    app = create_app()
    client = TestClient(app)

    response = client.get("/watchlist", headers={"Origin": "http://localhost:3000"})

    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-credentials" not in response.headers


def test_allowed_dev_origin_preflight_allows_post(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRADING_AI_CORS_ORIGINS", raising=False)
    app = create_app()
    client = TestClient(app)

    response = client.options(
        "/watchlist",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:3000"
    assert "access-control-allow-credentials" not in response.headers


def test_arbitrary_origin_is_not_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRADING_AI_CORS_ORIGINS", raising=False)
    app = create_app()
    client = TestClient(app)

    response = client.get("/watchlist", headers={"Origin": "http://evil.example"})

    assert "access-control-allow-origin" not in response.headers


def test_custom_cors_origins_replaces_dev_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_AI_CORS_ORIGINS", "https://app.example.com")
    app = create_app()
    client = TestClient(app)

    custom_origin_response = client.get(
        "/watchlist", headers={"Origin": "https://app.example.com"}
    )
    dev_default_response = client.get("/watchlist", headers={"Origin": "http://localhost:3000"})

    assert (
        custom_origin_response.headers.get("access-control-allow-origin")
        == "https://app.example.com"
    )
    assert "access-control-allow-origin" not in dev_default_response.headers
