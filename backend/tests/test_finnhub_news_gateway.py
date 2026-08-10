"""`FinnhubNewsGateway` tests — mock only the external provider boundary
(`httpx.MockTransport`, no extra dependency), never our own use cases
or repository.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from trading_ai.market_data.news_gateway import SOURCE, FinnhubNewsGateway
from trading_ai.market_data.types import (
    MarketDataMalformedResponseError,
    MarketDataRateLimitedError,
    MarketDataTimeoutError,
    MarketDataUnavailableError,
)

_FAKE_API_KEY = "test-secret-key-should-never-leak"

_NEWS_PAYLOAD: list[dict[str, Any]] = [
    {
        "category": "company",
        "datetime": 1786377132,
        "headline": "Apple Stock Falls on Downgrade",
        "id": 141175155,
        "image": "https://example.com/img1.jpg",
        "related": "AAPL",
        "source": "Yahoo",
        "summary": "Apple's stock fell after a broker downgrade.",
        "url": "https://finnhub.io/api/news?id=abc111",
    },
    {
        "category": "company",
        "datetime": 1786380004,
        "headline": "These dow jones stocks are moving in today's session",
        "id": 141175994,
        "image": "",
        "related": "AAPL",
        "source": "ChartMill",
        "summary": "Join us in exploring the top gainers and losers.",
        "url": "https://finnhub.io/api/news?id=abc222",
    },
]


def _gateway(handler: object) -> FinnhubNewsGateway:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return FinnhubNewsGateway(api_key=_FAKE_API_KEY, transport=transport)


@pytest.mark.anyio
async def test_get_instrument_news_maps_successful_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["symbol"] == "AAPL"
        assert "from" in request.url.params
        assert "to" in request.url.params
        return httpx.Response(200, json=_NEWS_PAYLOAD)

    news = await _gateway(handler).get_instrument_news("AAPL")

    assert news.ticker == "AAPL"
    assert news.source == SOURCE
    assert len(news.items) == 2
    first = news.items[0]
    assert first.id == "141175994"
    assert first.headline == "These dow jones stocks are moving in today's session"
    assert first.source == "ChartMill"
    assert first.url == "https://finnhub.io/api/news?id=abc222"
    assert first.summary == "Join us in exploring the top gainers and losers."
    assert first.published_at.tzinfo is not None


@pytest.mark.anyio
async def test_get_instrument_news_orders_newest_first_regardless_of_provider_order() -> None:
    """Payload above is already oldest-first (1786377132 < 1786380004);
    the gateway must reorder it, not trust the provider."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_NEWS_PAYLOAD)

    news = await _gateway(handler).get_instrument_news("AAPL")

    timestamps = [item.published_at for item in news.items]
    assert timestamps == sorted(timestamps, reverse=True)
    assert news.items[0].id == "141175994"
    assert news.items[-1].id == "141175155"


@pytest.mark.anyio
async def test_get_instrument_news_empty_items_returns_empty_tuple_not_an_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    news = await _gateway(handler).get_instrument_news("AAPL")

    assert news.items == ()


@pytest.mark.anyio
async def test_get_instrument_news_missing_optional_summary_is_none_not_empty_string() -> None:
    payload = [{**_NEWS_PAYLOAD[0], "summary": ""}]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    news = await _gateway(handler).get_instrument_news("AAPL")

    assert news.items[0].summary is None


@pytest.mark.anyio
async def test_get_instrument_news_missing_summary_key_is_none() -> None:
    payload = [{k: v for k, v in _NEWS_PAYLOAD[0].items() if k != "summary"}]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    news = await _gateway(handler).get_instrument_news("AAPL")

    assert news.items[0].summary is None


@pytest.mark.anyio
async def test_get_instrument_news_invalid_timestamp_skips_that_item_only() -> None:
    bad_item = {**_NEWS_PAYLOAD[0], "id": 999, "datetime": "not-a-timestamp"}
    payload = [bad_item, _NEWS_PAYLOAD[1]]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    news = await _gateway(handler).get_instrument_news("AAPL")

    assert len(news.items) == 1
    assert news.items[0].id == "141175994"


@pytest.mark.anyio
async def test_get_instrument_news_malformed_url_skips_that_item_only() -> None:
    bad_item = {**_NEWS_PAYLOAD[0], "id": 999, "url": "not a url at all"}
    payload = [bad_item, _NEWS_PAYLOAD[1]]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    news = await _gateway(handler).get_instrument_news("AAPL")

    assert len(news.items) == 1
    assert news.items[0].id == "141175994"


@pytest.mark.anyio
async def test_get_instrument_news_unsafe_url_scheme_skips_that_item_only() -> None:
    bad_item = {**_NEWS_PAYLOAD[0], "id": 999, "url": "javascript:alert(1)"}
    payload = [bad_item, _NEWS_PAYLOAD[1]]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    news = await _gateway(handler).get_instrument_news("AAPL")

    assert len(news.items) == 1
    assert news.items[0].id == "141175994"
    assert all(not item.url.startswith("javascript:") for item in news.items)


@pytest.mark.anyio
async def test_get_instrument_news_caps_at_default_limit() -> None:
    payload = [
        {**_NEWS_PAYLOAD[0], "id": i, "datetime": 1786377132 + i} for i in range(25)
    ]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    news = await _gateway(handler).get_instrument_news("AAPL")

    assert len(news.items) == 10


@pytest.mark.anyio
async def test_get_instrument_news_timeout_raises_timeout_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    with pytest.raises(MarketDataTimeoutError):
        await _gateway(handler).get_instrument_news("AAPL")


@pytest.mark.anyio
async def test_get_instrument_news_rate_limited_raises_rate_limited_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "limit exceeded"})

    with pytest.raises(MarketDataRateLimitedError):
        await _gateway(handler).get_instrument_news("AAPL")


@pytest.mark.anyio
async def test_get_instrument_news_bad_api_key_raises_unavailable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Invalid API key"})

    with pytest.raises(MarketDataUnavailableError):
        await _gateway(handler).get_instrument_news("AAPL")


@pytest.mark.anyio
async def test_get_instrument_news_provider_5xx_raises_unavailable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    with pytest.raises(MarketDataUnavailableError):
        await _gateway(handler).get_instrument_news("AAPL")


@pytest.mark.anyio
async def test_get_instrument_news_network_error_raises_unavailable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(MarketDataUnavailableError):
        await _gateway(handler).get_instrument_news("AAPL")


@pytest.mark.anyio
async def test_get_instrument_news_malformed_json_raises_malformed_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json at all")

    with pytest.raises(MarketDataMalformedResponseError):
        await _gateway(handler).get_instrument_news("AAPL")


@pytest.mark.anyio
async def test_get_instrument_news_non_array_payload_raises_malformed_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    with pytest.raises(MarketDataMalformedResponseError):
        await _gateway(handler).get_instrument_news("AAPL")


@pytest.mark.anyio
async def test_get_instrument_news_sends_api_key_as_header_not_query_param() -> None:
    seen_url = ""
    seen_auth_header = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_url, seen_auth_header
        seen_url = str(request.url)
        seen_auth_header = request.headers.get("X-Finnhub-Token", "")
        return httpx.Response(200, json=_NEWS_PAYLOAD)

    await _gateway(handler).get_instrument_news("AAPL")

    assert _FAKE_API_KEY not in seen_url
    assert seen_auth_header == _FAKE_API_KEY


@pytest.mark.anyio
async def test_get_instrument_news_no_secret_leakage_in_error_messages() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    with pytest.raises(MarketDataUnavailableError) as exc_info:
        await _gateway(handler).get_instrument_news("AAPL")

    assert _FAKE_API_KEY not in str(exc_info.value)
    assert _FAKE_API_KEY not in repr(exc_info.value)
