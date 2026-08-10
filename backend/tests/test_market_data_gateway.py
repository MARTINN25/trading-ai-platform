"""`TwelveDataGateway` tests — mock only the external provider boundary
(`httpx.MockTransport`, no extra dependency), never our own use cases
or repository.
"""

from __future__ import annotations

from datetime import timezone
from decimal import Decimal

import httpx
import pytest

from trading_ai.market_data.gateway import SOURCE, TwelveDataGateway
from trading_ai.market_data.types import (
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
