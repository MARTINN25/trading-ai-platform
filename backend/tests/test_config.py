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


def test_settings_default_cors_origins_is_local_dev_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TRADING_AI_CORS_ORIGINS", raising=False)

    settings = get_settings()

    assert settings.cors_origins == ("http://localhost:3000", "http://127.0.0.1:3000")


def test_settings_cors_origins_can_be_overridden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "TRADING_AI_CORS_ORIGINS", "https://app.example.com,https://admin.example.com"
    )

    settings = get_settings()

    assert settings.cors_origins == (
        "https://app.example.com",
        "https://admin.example.com",
    )


def test_settings_cors_origins_are_trimmed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "TRADING_AI_CORS_ORIGINS", "  https://app.example.com ,  https://admin.example.com  "
    )

    settings = get_settings()

    assert settings.cors_origins == (
        "https://app.example.com",
        "https://admin.example.com",
    )


def test_settings_cors_origins_drop_empty_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_AI_CORS_ORIGINS", "https://app.example.com,,  ,")

    settings = get_settings()

    assert settings.cors_origins == ("https://app.example.com",)


def test_settings_live_streaming_enabled_defaults_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRADING_AI_LIVE_STREAMING_ENABLED", raising=False)

    settings = get_settings()

    assert settings.market_data_live_streaming_enabled is True


def test_settings_live_streaming_enabled_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_AI_LIVE_STREAMING_ENABLED", "false")

    settings = get_settings()

    assert settings.market_data_live_streaming_enabled is False


def test_settings_live_poll_interval_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRADING_AI_LIVE_POLL_INTERVAL_SECONDS", raising=False)

    settings = get_settings()

    assert settings.market_data_live_poll_interval_seconds == 15.0


def test_settings_live_poll_interval_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_AI_LIVE_POLL_INTERVAL_SECONDS", "30")

    settings = get_settings()

    assert settings.market_data_live_poll_interval_seconds == 30.0
