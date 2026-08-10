"""API-boundary tests for `GET /instruments/{ticker}`.

Overrides `get_instrument_details_use_case` directly (not the gateway),
so these tests never touch httpx/asyncpg at all — same pattern as
`test_watchlist_api.py`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from trading_ai.api.routes.instruments import (
    get_instrument_details_use_case,
    get_instrument_price_history_use_case,
)
from trading_ai.main import create_app
from trading_ai.market_data.types import (
    InstrumentHistoryPeriod,
    InstrumentSnapshot,
    InvalidPeriodError,
    MarketDataRateLimitedError,
    MarketDataTimeoutError,
    MarketDataUnavailableError,
    PriceHistory,
    PricePoint,
    TickerUnsupportedError,
)
from trading_ai.watchlist.domain import InvalidTickerError

_FAKE_API_KEY = "test-secret-key-should-never-leak"


class _FakeGetInstrumentDetails:
    def __init__(
        self, result: InstrumentSnapshot | None = None, error: Exception | None = None
    ) -> None:
        self._result = result
        self._error = error
        self.received_ticker: str | None = None

    async def execute(self, raw_ticker: str) -> InstrumentSnapshot:
        self.received_ticker = raw_ticker
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def _override(app: FastAPI, fake_use_case: _FakeGetInstrumentDetails) -> None:
    app.dependency_overrides[get_instrument_details_use_case] = lambda: fake_use_case


class _FakeGetInstrumentPriceHistory:
    def __init__(
        self, result: PriceHistory | None = None, error: Exception | None = None
    ) -> None:
        self._result = result
        self._error = error
        self.received_args: tuple[str, str] | None = None

    async def execute(self, raw_ticker: str, raw_period: str) -> PriceHistory:
        self.received_args = (raw_ticker, raw_period)
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def _override_history(app: FastAPI, fake_use_case: _FakeGetInstrumentPriceHistory) -> None:
    app.dependency_overrides[get_instrument_price_history_use_case] = lambda: fake_use_case


def _sample_history(period: InstrumentHistoryPeriod = InstrumentHistoryPeriod.ONE_DAY) -> PriceHistory:
    base = datetime(2026, 8, 10, 15, 20, 0, tzinfo=timezone.utc)
    return PriceHistory(
        ticker="AAPL",
        period=period,
        source="twelvedata",
        points=(
            PricePoint(
                timestamp=base,
                open=Decimal("306.65"),
                high=Decimal("306.73"),
                low=Decimal("306.56"),
                close=Decimal("306.62"),
                volume=31152,
            ),
            PricePoint(
                timestamp=base.replace(minute=25),
                open=Decimal("306.61"),
                high=Decimal("306.69"),
                low=Decimal("306.43"),
                close=Decimal("306.53"),
                volume=48036,
            ),
        ),
    )


def test_get_instrument_details_success_returns_200() -> None:
    app = create_app()
    snapshot = InstrumentSnapshot(
        ticker="AAPL",
        price=Decimal("213.45"),
        change=Decimal("2.31"),
        change_percent=Decimal("1.09"),
        open=Decimal("210.00"),
        high=Decimal("214.20"),
        low=Decimal("209.50"),
        previous_close=Decimal("211.14"),
        volume=48_213_456,
        as_of=datetime.now(timezone.utc),
        source="twelvedata",
    )
    fake_use_case = _FakeGetInstrumentDetails(result=snapshot)
    _override(app, fake_use_case)
    client = TestClient(app)

    response = client.get("/instruments/AAPL")

    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "AAPL"
    assert Decimal(body["price"]) == Decimal("213.45")
    assert Decimal(body["open"]) == Decimal("210.00")
    assert body["volume"] == 48_213_456
    assert body["source"] == "twelvedata"
    assert fake_use_case.received_ticker == "AAPL"


def test_get_instrument_details_optional_fields_missing_are_null_not_zero() -> None:
    app = create_app()
    snapshot = InstrumentSnapshot(
        ticker="AAPL",
        price=Decimal("213.45"),
        change=Decimal("2.31"),
        change_percent=Decimal("1.09"),
        open=None,
        high=None,
        low=None,
        previous_close=None,
        volume=None,
        as_of=datetime.now(timezone.utc),
        source="twelvedata",
    )
    _override(app, _FakeGetInstrumentDetails(result=snapshot))
    client = TestClient(app)

    response = client.get("/instruments/AAPL")

    assert response.status_code == 200
    body = response.json()
    assert body["open"] is None
    assert body["volume"] is None


def test_get_instrument_details_unsupported_ticker_returns_404() -> None:
    app = create_app()
    _override(app, _FakeGetInstrumentDetails(error=TickerUnsupportedError("NOTATICKER")))
    client = TestClient(app)

    response = client.get("/instruments/NOTATICKER")

    assert response.status_code == 404
    body = response.text.lower()
    assert "traceback" not in body
    assert "tickerunsupportederror" not in body


def test_get_instrument_details_invalid_ticker_returns_422() -> None:
    app = create_app()
    _override(app, _FakeGetInstrumentDetails(error=InvalidTickerError("ticker must not be empty")))
    client = TestClient(app)

    response = client.get("/instruments/ ")

    assert response.status_code == 422


def test_get_instrument_details_provider_unavailable_returns_503() -> None:
    app = create_app()
    _override(app, _FakeGetInstrumentDetails(error=MarketDataUnavailableError("boom")))
    client = TestClient(app)

    response = client.get("/instruments/AAPL")

    assert response.status_code == 503
    assert "boom" not in response.text


def test_get_instrument_details_rate_limited_returns_503() -> None:
    app = create_app()
    _override(app, _FakeGetInstrumentDetails(error=MarketDataRateLimitedError("limit")))
    client = TestClient(app)

    response = client.get("/instruments/AAPL")

    assert response.status_code == 503


def test_get_instrument_details_timeout_returns_504() -> None:
    app = create_app()
    _override(app, _FakeGetInstrumentDetails(error=MarketDataTimeoutError("slow")))
    client = TestClient(app)

    response = client.get("/instruments/AAPL")

    assert response.status_code == 504


def test_get_instrument_details_without_provider_configured_returns_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TRADING_AI_MARKET_DATA_API_KEY", raising=False)
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/instruments/AAPL")

    assert response.status_code == 503


def test_get_instrument_details_response_never_contains_api_key() -> None:
    app = create_app()
    snapshot = InstrumentSnapshot(
        ticker="AAPL",
        price=Decimal("213.45"),
        change=Decimal("2.31"),
        change_percent=Decimal("1.09"),
        open=Decimal("210.00"),
        high=Decimal("214.20"),
        low=Decimal("209.50"),
        previous_close=Decimal("211.14"),
        volume=48_213_456,
        as_of=datetime.now(timezone.utc),
        source="twelvedata",
    )
    _override(app, _FakeGetInstrumentDetails(result=snapshot))
    client = TestClient(app)

    response = client.get("/instruments/AAPL")

    assert _FAKE_API_KEY not in response.text
    assert "api.twelvedata.com" not in response.text


def test_get_instrument_price_history_success_returns_ordered_points() -> None:
    app = create_app()
    fake_use_case = _FakeGetInstrumentPriceHistory(result=_sample_history())
    _override_history(app, fake_use_case)
    client = TestClient(app)

    response = client.get("/instruments/AAPL/history?period=1D")

    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "AAPL"
    assert body["period"] == "1D"
    assert body["source"] == "twelvedata"
    assert len(body["points"]) == 2
    assert Decimal(body["points"][0]["close"]) == Decimal("306.62")
    assert "open" not in body["points"][0]
    assert fake_use_case.received_args == ("AAPL", "1D")


def test_get_instrument_price_history_5d_and_1m_periods_pass_through() -> None:
    app = create_app()
    for period_value, period_enum in (
        ("5D", InstrumentHistoryPeriod.FIVE_DAY),
        ("1M", InstrumentHistoryPeriod.ONE_MONTH),
    ):
        fake_use_case = _FakeGetInstrumentPriceHistory(result=_sample_history(period_enum))
        _override_history(app, fake_use_case)
        client = TestClient(app)

        response = client.get(f"/instruments/AAPL/history?period={period_value}")

        assert response.status_code == 200
        assert response.json()["period"] == period_value
        assert fake_use_case.received_args == ("AAPL", period_value)


def test_get_instrument_price_history_empty_points_is_200_not_error() -> None:
    app = create_app()
    empty_history = PriceHistory(
        ticker="AAPL", period=InstrumentHistoryPeriod.ONE_DAY, source="twelvedata", points=()
    )
    _override_history(app, _FakeGetInstrumentPriceHistory(result=empty_history))
    client = TestClient(app)

    response = client.get("/instruments/AAPL/history?period=1D")

    assert response.status_code == 200
    assert response.json()["points"] == []


def test_get_instrument_price_history_invalid_period_returns_422() -> None:
    app = create_app()
    _override_history(
        app,
        _FakeGetInstrumentPriceHistory(
            error=InvalidPeriodError("period must be one of: 1D, 5D, 1M")
        ),
    )
    client = TestClient(app)

    response = client.get("/instruments/AAPL/history?period=2Y")

    assert response.status_code == 422


def test_get_instrument_price_history_missing_period_returns_422() -> None:
    app = create_app()
    _override_history(app, _FakeGetInstrumentPriceHistory(result=_sample_history()))
    client = TestClient(app)

    response = client.get("/instruments/AAPL/history")

    assert response.status_code == 422


def test_get_instrument_price_history_unsupported_ticker_returns_404() -> None:
    app = create_app()
    _override_history(
        app, _FakeGetInstrumentPriceHistory(error=TickerUnsupportedError("NOTATICKER"))
    )
    client = TestClient(app)

    response = client.get("/instruments/NOTATICKER/history?period=1D")

    assert response.status_code == 404


def test_get_instrument_price_history_timeout_returns_504() -> None:
    app = create_app()
    _override_history(app, _FakeGetInstrumentPriceHistory(error=MarketDataTimeoutError("slow")))
    client = TestClient(app)

    response = client.get("/instruments/AAPL/history?period=1D")

    assert response.status_code == 504


def test_get_instrument_price_history_rate_limited_or_unavailable_returns_503() -> None:
    app = create_app()
    for error in (MarketDataRateLimitedError("limit"), MarketDataUnavailableError("boom")):
        _override_history(app, _FakeGetInstrumentPriceHistory(error=error))
        client = TestClient(app)

        response = client.get("/instruments/AAPL/history?period=1D")

        assert response.status_code == 503
        assert "boom" not in response.text


def test_get_instrument_price_history_without_provider_configured_returns_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TRADING_AI_MARKET_DATA_API_KEY", raising=False)
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/instruments/AAPL/history?period=1D")

    assert response.status_code == 503


def test_get_instrument_price_history_response_never_contains_api_key() -> None:
    app = create_app()
    _override_history(app, _FakeGetInstrumentPriceHistory(result=_sample_history()))
    client = TestClient(app)

    response = client.get("/instruments/AAPL/history?period=1D")

    assert _FAKE_API_KEY not in response.text
    assert "api.twelvedata.com" not in response.text
