"""Opt-in integration test against a real PostgreSQL instance.

Skipped by default — does not block the normal test suite and never
guesses credentials. To run it, set `TRADING_AI_TEST_DATABASE_URL` to
a real, reachable PostgreSQL DSN before invoking pytest, e.g.:

    TRADING_AI_TEST_DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db \\
        python -m pytest -m integration tests/integration

This test performs only a read-only `SELECT 1` via `/ready` — it does
not run migrations and does not create schema.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

_TEST_DATABASE_URL = os.environ.get("TRADING_AI_TEST_DATABASE_URL")


@pytest.mark.skipif(
    not _TEST_DATABASE_URL,
    reason=(
        "TRADING_AI_TEST_DATABASE_URL is not set - skipping real "
        "PostgreSQL integration test (opt-in only)."
    ),
)
def test_ready_reports_ok_against_a_real_postgresql_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _TEST_DATABASE_URL is not None
    monkeypatch.setenv("TRADING_AI_DATABASE_URL", _TEST_DATABASE_URL)

    from trading_ai.main import create_app

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
