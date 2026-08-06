from __future__ import annotations

import pytest

from trading_ai.config import get_required_database_url, get_settings


def test_settings_reads_database_url_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "TRADING_AI_DATABASE_URL",
        "postgresql+asyncpg://someuser:somepassword@db-host:5432/trading_ai",
    )

    settings = get_settings()

    assert (
        settings.database_url
        == "postgresql+asyncpg://someuser:somepassword@db-host:5432/trading_ai"
    )


def test_settings_database_url_is_none_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TRADING_AI_DATABASE_URL", raising=False)

    settings = get_settings()

    assert settings.database_url is None


def test_get_required_database_url_raises_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TRADING_AI_DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError):
        get_required_database_url()


def test_get_required_database_url_returns_value_when_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "TRADING_AI_DATABASE_URL",
        "postgresql+asyncpg://someuser:somepassword@db-host:5432/trading_ai",
    )

    url = get_required_database_url()

    assert url == "postgresql+asyncpg://someuser:somepassword@db-host:5432/trading_ai"
