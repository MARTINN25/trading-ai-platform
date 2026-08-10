"""Finnhub company-news gateway.

The only place in the codebase that imports `httpx` for Finnhub calls
or knows Finnhub's URL/response shape — mirrors `gateway.py`'s
boundary role for Twelve Data (ADR-0007 §22: the adapter is the sole
SDK/HTTP boundary; application code depends only on `types.py`'s
contract).

Finnhub is a *second*, separate implementation-decision provider used
only for instrument news. Twelve Data was checked first and has no
usable news product: its full documented endpoint catalog has no
"News" section at all, and the closest item ("Press releases," under
Fundamentals) was confirmed live to return neither a `source` nor a
`url` field — both hard requirements here — plus raw HTML press-release
bodies rather than a real summary. Finnhub's `company-news` endpoint
was confirmed live (real account, real call) before writing this file:
header-based auth works, the response is a JSON array with
`headline`/`source`/`datetime`/`url`/`summary` fields, ordered
newest-first by default, and an unrecognized/unsupported ticker
returns `200 []` rather than a distinguishable "not found" error (so
this gateway never raises `TickerUnsupportedError` — an empty list is
the only, and correct, "nothing found" signal, matching this
endpoint's actual behavior rather than inventing a distinction Finnhub
doesn't make).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from trading_ai.market_data.types import (
    InstrumentNews,
    InstrumentNewsItem,
    MarketDataError,
    MarketDataMalformedResponseError,
    MarketDataRateLimitedError,
    MarketDataTimeoutError,
    MarketDataUnavailableError,
)

logger = logging.getLogger(__name__)

SOURCE = "finnhub"
_BASE_URL = "https://finnhub.io/api/v1"
_REQUEST_TIMEOUT_SECONDS = 5.0

# One request per instrument-news load (task scope §3, §10) — no
# widening/retry logic, so a single fixed lookback window is chosen
# once. 7 days reliably returns items for actively-covered US equities
# (confirmed live: AAPL returned 247 items over a comparable window)
# without needing a second call for thin-coverage tickers to still get
# a chance at some results.
_LOOKBACK_DAYS = 7

# Fixed, bounded cap (task scope §3, §8: "5-10 последних новостей
# максимум"). Finnhub's company-news has no server-side `limit`
# parameter, so the cap is applied client-side after sorting.
_DEFAULT_LIMIT = 10

_SAFE_URL_SCHEMES = ("http", "https")


class FinnhubNewsGateway:
    """Concrete gateway for Finnhub. One provider, one class — no generic framework."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = _BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        # Injectable only for tests (`httpx.MockTransport`) — `None`
        # means httpx's real network transport, unchanged in production.
        self._transport = transport

    async def get_instrument_news(self, ticker: str) -> InstrumentNews:
        started = time.monotonic()
        try:
            response = await self._fetch_raw(ticker)
            items = self._parse_news(ticker, response)
        except MarketDataError as exc:
            self._log(ticker, started, status=type(exc).__name__)
            raise
        self._log(ticker, started, status="ok", items_count=len(items))
        return InstrumentNews(ticker=ticker, source=SOURCE, items=tuple(items))

    async def _fetch_raw(self, ticker: str) -> httpx.Response:
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=_LOOKBACK_DAYS)
        try:
            async with httpx.AsyncClient(
                timeout=_REQUEST_TIMEOUT_SECONDS, transport=self._transport
            ) as client:
                response = await client.get(
                    f"{self._base_url}/company-news",
                    params={
                        "symbol": ticker,
                        "from": start.isoformat(),
                        "to": today.isoformat(),
                    },
                    # Header, not Finnhub's documented `token` query
                    # param — same reasoning as the Twelve Data gateway
                    # (see gateway.py): keeps the key out of every URL,
                    # so it never ends up in httpx/proxy request-line
                    # logging by default.
                    headers={"X-Finnhub-Token": self._api_key},
                )
        except httpx.TimeoutException as exc:
            raise MarketDataTimeoutError(f"timeout fetching news for {ticker}") from exc
        except httpx.HTTPError as exc:
            raise MarketDataUnavailableError(
                f"network error fetching news for {ticker}"
            ) from exc
        return response

    def _parse_news(self, ticker: str, response: httpx.Response) -> list[InstrumentNewsItem]:
        if response.status_code == 429:
            raise MarketDataRateLimitedError("provider rate limit exceeded")
        if response.status_code in (401, 403):
            # Bad/missing API key — confirmed live (401 body
            # `{"error": "..."}`). Never surfaced with provider
            # wording; treated as provider-side unavailability.
            raise MarketDataUnavailableError("provider rejected the request")
        if response.status_code >= 500:
            raise MarketDataUnavailableError(f"provider returned {response.status_code}")

        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise MarketDataMalformedResponseError(
                "provider response was not valid JSON"
            ) from exc

        if not response.is_success:
            raise MarketDataUnavailableError(f"provider returned {response.status_code}")

        if not isinstance(payload, list):
            raise MarketDataMalformedResponseError("provider response was not a JSON array")

        items: list[InstrumentNewsItem] = []
        for raw_item in payload:
            item = _parse_news_item(raw_item, ticker)
            if item is not None:
                items.append(item)

        # Defensive, not just a request hint (same rule as
        # `gateway._parse_history`): never trust provider ordering,
        # even though Finnhub's company-news is empirically
        # newest-first already.
        items.sort(key=lambda item: item.published_at, reverse=True)
        return items[:_DEFAULT_LIMIT]

    def _log(
        self, ticker: str, started: float, *, status: str, items_count: int | None = None
    ) -> None:
        """Minimal observability per call (ADR-0009 §22, §48-style fields).

        Never includes the API key, the full request URL/query string,
        or the raw provider payload/article content — only the safe,
        fixed fields below.
        """
        latency_ms = (time.monotonic() - started) * 1000
        if items_count is None:
            logger.info(
                "market_data_news operation=get_instrument_news ticker=%s source=%s "
                "status=%s latency_ms=%.1f",
                ticker,
                SOURCE,
                status,
                latency_ms,
            )
        else:
            logger.info(
                "market_data_news operation=get_instrument_news ticker=%s source=%s "
                "status=%s latency_ms=%.1f items_count=%d",
                ticker,
                SOURCE,
                status,
                latency_ms,
                items_count,
            )


def _parse_news_item(raw: Any, ticker: str) -> InstrumentNewsItem | None:
    """Best-effort per-item parse.

    Returns `None` (skip this one item) rather than failing the whole
    news list — a malformed timestamp, missing headline, or unsafe URL
    on one item must never take down the rest of a real, otherwise-good
    response (task scope §11: these are per-item test cases, not
    whole-response failures — mirrors how `PriceChart.tsx` skips
    unplottable points instead of crashing the chart).
    """
    if not isinstance(raw, dict):
        return None
    try:
        news_id = str(raw["id"])
        headline = str(raw["headline"]).strip()
        source = str(raw["source"]).strip()
        published_at = datetime.fromtimestamp(int(raw["datetime"]), tz=timezone.utc)
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        return None
    if not news_id or not headline or not source:
        return None

    url = _validate_article_url(raw.get("url"))
    if url is None:
        return None

    raw_summary = raw.get("summary")
    summary = (
        raw_summary.strip() if isinstance(raw_summary, str) and raw_summary.strip() else None
    )

    return InstrumentNewsItem(
        id=news_id,
        ticker=ticker,
        headline=headline,
        source=source,
        published_at=published_at,
        url=url,
        summary=summary,
    )


def _validate_article_url(value: Any) -> str | None:
    """Only `http://`/`https://` survives (task scope §6: URL security).

    `javascript:`, `data:`, `file:`, and anything else — including a
    non-string value or a string with no host — is rejected outright,
    never passed through just because the provider sent it.
    """
    if not isinstance(value, str):
        return None
    try:
        parsed = urlparse(value)
    except ValueError:
        return None
    if parsed.scheme not in _SAFE_URL_SCHEMES or not parsed.netloc:
        return None
    return value
