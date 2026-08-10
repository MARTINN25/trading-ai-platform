"""`TwelveDataGateway` tests — mock only the external provider boundary
(`httpx.MockTransport`, no extra dependency), never our own use cases
or repository.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx
import pytest

from trading_ai.market_data.gateway import SOURCE, TwelveDataGateway
from trading_ai.market_data.types import (
    InstrumentHistoryPeriod,
    MarketDataMalformedResponseError,
    MarketDataRateLimitedError,
    MarketDataTimeoutError,
    MarketDataUnavailableError,
    TickerUnsupportedError,
)

_FAKE_API_KEY = "test-secret-key-should-never-leak"

_SUCCESS_PAYLOAD = {
    "symbol": "AAPL",
    "name": "Apple Inc",
    "exchange": "NASDAQ",
    "currency": "USD",
    "datetime": "2026-08-10",
    "timestamp": 1_754_812_800,
    "close": "213.45000",
    "previous_close": "211.14000",
    "change": "2.31000",
    "percent_change": "1.09400",
    "is_market_open": False,
}

_SNAPSHOT_PAYLOAD = {
    **_SUCCESS_PAYLOAD,
    "open": "210.00000",
    "high": "214.20000",
    "low": "209.50000",
    "volume": "48213456",
}

_HISTORY_PAYLOAD: dict[str, Any] = {
    "meta": {
        "symbol": "AAPL",
        "interval": "5min",
        "currency": "USD",
        "exchange_timezone": "America/New_York",
        "exchange": "NASDAQ",
        "mic_code": "XNGS",
        "type": "Common Stock",
    },
    "values": [
        {
            "datetime": "2026-08-10 15:20:00",
            "open": "306.65",
            "high": "306.735",
            "low": "306.565",
            "close": "306.625",
            "volume": "31152",
        },
        {
            "datetime": "2026-08-10 15:25:00",
            "open": "306.61",
            "high": "306.69",
            "low": "306.43",
            "close": "306.535",
            "volume": "48036",
        },
        {
            "datetime": "2026-08-10 15:30:00",
            "open": "306.53",
            "high": "306.6",
            "low": "306.42",
            "close": "306.59",
            "volume": "54604",
        },
    ],
    "status": "ok",
}


def _gateway(handler: object) -> TwelveDataGateway:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return TwelveDataGateway(api_key=_FAKE_API_KEY, transport=transport)


@pytest.mark.anyio
async def test_get_quote_maps_successful_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["symbol"] == "AAPL"
        return httpx.Response(200, json=_SUCCESS_PAYLOAD)

    quote = await _gateway(handler).get_quote("AAPL")

    assert quote.ticker == "AAPL"
    assert quote.price == Decimal("213.45000")
    assert quote.change == Decimal("2.31000")
    assert quote.change_percent == Decimal("1.09400")
    assert quote.source == SOURCE
    assert quote.as_of.tzinfo is not None


@pytest.mark.anyio
async def test_get_quote_sends_api_key_as_header_not_query_param() -> None:
    """Regression test for a real leak found during live verification:
    httpx's own request logging writes the full URL (query params
    included) at INFO level. A query-param API key would show up in
    our own logs even though our code never logs it directly. The key
    must travel as a header instead — never part of the URL."""
    seen_url = ""
    seen_auth_header = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_url, seen_auth_header
        seen_url = str(request.url)
        seen_auth_header = request.headers.get("Authorization", "")
        return httpx.Response(200, json=_SUCCESS_PAYLOAD)

    await _gateway(handler).get_quote("AAPL")

    assert _FAKE_API_KEY not in seen_url
    assert seen_auth_header == f"apikey {_FAKE_API_KEY}"


@pytest.mark.anyio
async def test_get_quote_provider_5xx_raises_unavailable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    with pytest.raises(MarketDataUnavailableError):
        await _gateway(handler).get_quote("AAPL")


@pytest.mark.anyio
async def test_get_quote_network_error_raises_unavailable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(MarketDataUnavailableError):
        await _gateway(handler).get_quote("AAPL")


@pytest.mark.anyio
async def test_get_quote_timeout_raises_timeout_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    with pytest.raises(MarketDataTimeoutError):
        await _gateway(handler).get_quote("AAPL")


@pytest.mark.anyio
async def test_get_quote_rate_limited_raises_rate_limited_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"code": 429, "message": "limit", "status": "error"})

    with pytest.raises(MarketDataRateLimitedError):
        await _gateway(handler).get_quote("AAPL")


@pytest.mark.anyio
async def test_get_quote_unsupported_ticker_via_404() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"code": 404, "message": "not found", "status": "error"})

    with pytest.raises(TickerUnsupportedError):
        await _gateway(handler).get_quote("NOTATICKER")


@pytest.mark.anyio
async def test_get_quote_unsupported_ticker_via_200_error_body() -> None:
    """Twelve Data documents real HTTP status codes, but some free-tier
    error paths respond 200 with an error-shaped body — handled the
    same way as a real 400/404."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"code": 400, "message": "**symbol** not found", "status": "error"},
        )

    with pytest.raises(TickerUnsupportedError):
        await _gateway(handler).get_quote("NOTATICKER")


@pytest.mark.anyio
async def test_get_quote_malformed_json_raises_malformed_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json at all")

    with pytest.raises(MarketDataMalformedResponseError):
        await _gateway(handler).get_quote("AAPL")


@pytest.mark.anyio
async def test_get_quote_missing_fields_raises_malformed_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"symbol": "AAPL"})

    with pytest.raises(MarketDataMalformedResponseError):
        await _gateway(handler).get_quote("AAPL")


@pytest.mark.anyio
async def test_no_secret_leakage_in_error_messages() -> None:
    """The API key must never appear in a raised exception's message,
    across every failure path exercised above."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    with pytest.raises(MarketDataUnavailableError) as exc_info:
        await _gateway(handler).get_quote("AAPL")

    assert _FAKE_API_KEY not in str(exc_info.value)
    assert _FAKE_API_KEY not in repr(exc_info.value)


@pytest.mark.anyio
async def test_get_instrument_snapshot_maps_successful_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["symbol"] == "AAPL"
        return httpx.Response(200, json=_SNAPSHOT_PAYLOAD)

    snapshot = await _gateway(handler).get_instrument_snapshot("AAPL")

    assert snapshot.ticker == "AAPL"
    assert snapshot.price == Decimal("213.45000")
    assert snapshot.change == Decimal("2.31000")
    assert snapshot.change_percent == Decimal("1.09400")
    assert snapshot.open == Decimal("210.00000")
    assert snapshot.high == Decimal("214.20000")
    assert snapshot.low == Decimal("209.50000")
    assert snapshot.previous_close == Decimal("211.14000")
    assert snapshot.volume == 48_213_456
    assert snapshot.source == SOURCE
    assert snapshot.as_of.tzinfo is not None


@pytest.mark.anyio
async def test_get_instrument_snapshot_missing_optional_field_is_none_not_zero() -> None:
    """A field the provider didn't return (e.g. no volume for this
    instrument type) must surface as `None`, never a guessed `0` —
    task scope: never invent a value the provider didn't give."""

    payload = {k: v for k, v in _SNAPSHOT_PAYLOAD.items() if k != "volume"}

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    snapshot = await _gateway(handler).get_instrument_snapshot("AAPL")

    assert snapshot.volume is None
    assert snapshot.open == Decimal("210.00000")


@pytest.mark.anyio
async def test_get_instrument_snapshot_unparseable_optional_field_is_none() -> None:
    payload = {**_SNAPSHOT_PAYLOAD, "high": "not-a-number"}

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    snapshot = await _gateway(handler).get_instrument_snapshot("AAPL")

    assert snapshot.high is None
    assert snapshot.low == Decimal("209.50000")


@pytest.mark.anyio
async def test_get_instrument_snapshot_unsupported_ticker_via_404() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"code": 404, "message": "not found", "status": "error"})

    with pytest.raises(TickerUnsupportedError):
        await _gateway(handler).get_instrument_snapshot("NOTATICKER")


@pytest.mark.anyio
async def test_get_instrument_snapshot_rate_limited_raises_rate_limited_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"code": 429, "message": "limit", "status": "error"})

    with pytest.raises(MarketDataRateLimitedError):
        await _gateway(handler).get_instrument_snapshot("AAPL")


@pytest.mark.anyio
async def test_get_instrument_snapshot_timeout_raises_timeout_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    with pytest.raises(MarketDataTimeoutError):
        await _gateway(handler).get_instrument_snapshot("AAPL")


@pytest.mark.anyio
async def test_get_instrument_snapshot_malformed_json_raises_malformed_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json at all")

    with pytest.raises(MarketDataMalformedResponseError):
        await _gateway(handler).get_instrument_snapshot("AAPL")


@pytest.mark.anyio
async def test_get_instrument_snapshot_missing_core_fields_raises_malformed_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"symbol": "AAPL"})

    with pytest.raises(MarketDataMalformedResponseError):
        await _gateway(handler).get_instrument_snapshot("AAPL")


@pytest.mark.anyio
async def test_get_instrument_snapshot_sends_api_key_as_header_not_query_param() -> None:
    seen_url = ""
    seen_auth_header = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_url, seen_auth_header
        seen_url = str(request.url)
        seen_auth_header = request.headers.get("Authorization", "")
        return httpx.Response(200, json=_SNAPSHOT_PAYLOAD)

    await _gateway(handler).get_instrument_snapshot("AAPL")

    assert _FAKE_API_KEY not in seen_url
    assert seen_auth_header == f"apikey {_FAKE_API_KEY}"


@pytest.mark.anyio
async def test_get_price_history_maps_successful_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["symbol"] == "AAPL"
        assert request.url.params["interval"] == "5min"
        assert request.url.params["timezone"] == "UTC"
        return httpx.Response(200, json=_HISTORY_PAYLOAD)

    history = await _gateway(handler).get_price_history("AAPL", InstrumentHistoryPeriod.ONE_DAY)

    assert history.ticker == "AAPL"
    assert history.period == InstrumentHistoryPeriod.ONE_DAY
    assert history.source == SOURCE
    assert len(history.points) == 3
    first, _, last = history.points
    assert first.close == Decimal("306.625")
    assert first.timestamp == datetime(2026, 8, 10, 15, 20, 0, tzinfo=timezone.utc)
    assert last.close == Decimal("306.59")
    assert first.open == Decimal("306.65")
    assert first.volume == 31152


@pytest.mark.anyio
async def test_get_price_history_normalizes_reversed_provider_order_to_asc() -> None:
    reversed_payload = {**_HISTORY_PAYLOAD, "values": list(reversed(_HISTORY_PAYLOAD["values"]))}

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=reversed_payload)

    history = await _gateway(handler).get_price_history("AAPL", InstrumentHistoryPeriod.ONE_DAY)

    timestamps = [point.timestamp for point in history.points]
    assert timestamps == sorted(timestamps)
    assert history.points[0].close == Decimal("306.625")
    assert history.points[-1].close == Decimal("306.59")


@pytest.mark.anyio
async def test_get_price_history_single_point_is_handled_safely() -> None:
    payload = {**_HISTORY_PAYLOAD, "values": _HISTORY_PAYLOAD["values"][:1]}

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    history = await _gateway(handler).get_price_history("AAPL", InstrumentHistoryPeriod.ONE_DAY)

    assert len(history.points) == 1


@pytest.mark.anyio
async def test_get_price_history_empty_values_returns_empty_points_not_an_error() -> None:
    payload = {**_HISTORY_PAYLOAD, "values": []}

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    history = await _gateway(handler).get_price_history("AAPL", InstrumentHistoryPeriod.ONE_DAY)

    assert history.points == ()


@pytest.mark.anyio
async def test_get_price_history_daily_interval_date_only_timestamp() -> None:
    payload = {
        "meta": {"symbol": "AAPL", "interval": "1day"},
        "values": [{"datetime": "2026-08-10", "open": "306.74", "high": "307.46",
                     "low": "304.64", "close": "306.59", "volume": "3138892"}],
        "status": "ok",
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    history = await _gateway(handler).get_price_history("AAPL", InstrumentHistoryPeriod.ONE_MONTH)

    assert history.points[0].timestamp == datetime(2026, 8, 10, 0, 0, 0, tzinfo=timezone.utc)


@pytest.mark.anyio
async def test_get_price_history_missing_close_raises_malformed_error() -> None:
    payload = {
        **_HISTORY_PAYLOAD,
        "values": [{"datetime": "2026-08-10 15:20:00", "open": "306.65"}],
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(MarketDataMalformedResponseError):
        await _gateway(handler).get_price_history("AAPL", InstrumentHistoryPeriod.ONE_DAY)


@pytest.mark.anyio
async def test_get_price_history_invalid_timestamp_raises_malformed_error() -> None:
    payload = {
        **_HISTORY_PAYLOAD,
        "values": [{"datetime": "not-a-date", "close": "306.59"}],
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(MarketDataMalformedResponseError):
        await _gateway(handler).get_price_history("AAPL", InstrumentHistoryPeriod.ONE_DAY)


@pytest.mark.anyio
async def test_get_price_history_missing_values_key_raises_malformed_error() -> None:
    payload = {"meta": {"symbol": "AAPL"}, "status": "ok"}

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(MarketDataMalformedResponseError):
        await _gateway(handler).get_price_history("AAPL", InstrumentHistoryPeriod.ONE_DAY)


@pytest.mark.anyio
async def test_get_price_history_optional_field_missing_is_none_not_zero() -> None:
    payload = {
        **_HISTORY_PAYLOAD,
        "values": [{"datetime": "2026-08-10 15:20:00", "close": "306.59"}],
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    history = await _gateway(handler).get_price_history("AAPL", InstrumentHistoryPeriod.ONE_DAY)

    assert history.points[0].open is None
    assert history.points[0].volume is None
    assert history.points[0].close == Decimal("306.59")


@pytest.mark.anyio
async def test_get_price_history_timeout_raises_timeout_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    with pytest.raises(MarketDataTimeoutError):
        await _gateway(handler).get_price_history("AAPL", InstrumentHistoryPeriod.ONE_DAY)


@pytest.mark.anyio
async def test_get_price_history_rate_limited_raises_rate_limited_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"code": 429, "message": "limit", "status": "error"})

    with pytest.raises(MarketDataRateLimitedError):
        await _gateway(handler).get_price_history("AAPL", InstrumentHistoryPeriod.ONE_DAY)


@pytest.mark.anyio
async def test_get_price_history_unsupported_ticker_via_404() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"code": 404, "message": "not found", "status": "error"})

    with pytest.raises(TickerUnsupportedError):
        await _gateway(handler).get_price_history("NOTATICKER", InstrumentHistoryPeriod.ONE_DAY)


@pytest.mark.anyio
async def test_get_price_history_sends_api_key_as_header_not_query_param() -> None:
    seen_url = ""
    seen_auth_header = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_url, seen_auth_header
        seen_url = str(request.url)
        seen_auth_header = request.headers.get("Authorization", "")
        return httpx.Response(200, json=_HISTORY_PAYLOAD)

    await _gateway(handler).get_price_history("AAPL", InstrumentHistoryPeriod.ONE_DAY)

    assert _FAKE_API_KEY not in seen_url
    assert seen_auth_header == f"apikey {_FAKE_API_KEY}"


@pytest.mark.anyio
async def test_get_price_history_no_secret_leakage_in_error_messages() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    with pytest.raises(MarketDataUnavailableError) as exc_info:
        await _gateway(handler).get_price_history("AAPL", InstrumentHistoryPeriod.ONE_DAY)

    assert _FAKE_API_KEY not in str(exc_info.value)
    assert _FAKE_API_KEY not in repr(exc_info.value)
