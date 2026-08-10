"""Twelve Data market-data gateway.

The only place in the codebase that imports `httpx` for provider calls
or knows Twelve Data's URL/response shape (ADR-0007 §22: the adapter
is the sole SDK/HTTP boundary; watchlist application code depends only
on `types.py`'s contract).

Twelve Data was chosen as an *implementation decision* for this
vertical slice (official REST API, documented free tier, no scraping/
reverse-engineered endpoints) — not an ADR-level commitment. See
README for the full rationale and the open question this leaves for a
future formal decision if/when this becomes a hard platform
dependency.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from trading_ai.market_data.types import (
    MarketDataError,
    MarketDataMalformedResponseError,
    MarketDataRateLimitedError,
    MarketDataTimeoutError,
    MarketDataUnavailableError,
    MarketQuote,
    TickerUnsupportedError,
)

logger = logging.getLogger(__name__)

SOURCE = "twelvedata"
_BASE_URL = "https://api.twelvedata.com"

# Bounded, single attempt — no automatic retry (task scope: "не делать
# бесконечные retry"). A user-visible "Обновить данные" action is the
# retry mechanism, not this gateway.
_REQUEST_TIMEOUT_SECONDS = 5.0


class TwelveDataGateway:
    """Concrete gateway for Twelve Data. One provider, one class — no generic framework."""

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

    async def get_quote(self, ticker: str) -> MarketQuote:
        started = time.monotonic()
        try:
            quote = await self._fetch(ticker)
        except MarketDataError as exc:
            self._log(ticker, started, status=type(exc).__name__)
            raise
        self._log(ticker, started, status="ok")
        return quote

    async def _fetch(self, ticker: str) -> MarketQuote:
        try:
            async with httpx.AsyncClient(
                timeout=_REQUEST_TIMEOUT_SECONDS, transport=self._transport
            ) as client:
                response = await client.get(
                    f"{self._base_url}/quote",
                    params={"symbol": ticker},
                    # Header, not a query param: Twelve Data documents
                    # both, but a query param ends up in every URL —
                    # logged by httpx/proxies/access logs by default
                    # far more often than a header is. Keeping the key
                    # out of the URL is defense in depth, independent
                    # of also silencing httpx's own request logging
                    # (see trading_ai.logging.configure_logging).
                    headers={"Authorization": f"apikey {self._api_key}"},
                )
        except httpx.TimeoutException as exc:
            raise MarketDataTimeoutError(f"timeout fetching quote for {ticker}") from exc
        except httpx.HTTPError as exc:
            # Network-level failure (connection refused/reset/DNS/etc).
            # Never includes the request URL/headers (which carry the
            # API key) in the raised message.
            raise MarketDataUnavailableError(
                f"network error fetching quote for {ticker}"
            ) from exc

        return self._parse_response(ticker, response)

    def _parse_response(self, ticker: str, response: httpx.Response) -> MarketQuote:
        if response.status_code == 429:
            raise MarketDataRateLimitedError("provider rate limit exceeded")
        if response.status_code in (401, 403):
            # Auth/permission problem (e.g. bad API key) — never
            # surfaced with provider wording; treated as provider-side
            # unavailability from the caller's point of view.
            raise MarketDataUnavailableError("provider rejected the request")
        if response.status_code == 404:
            raise TickerUnsupportedError(f"ticker not supported: {ticker}")
        if response.status_code >= 500:
            raise MarketDataUnavailableError(f"provider returned {response.status_code}")

        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise MarketDataMalformedResponseError(
                "provider response was not valid JSON"
            ) from exc

        if isinstance(payload, dict) and payload.get("status") == "error":
            # Twelve Data documents real HTTP status codes for errors,
            # but some free-tier error paths respond 200 with this
            # body shape instead — handled defensively either way.
            code = payload.get("code")
            if code in (400, 404):
                raise TickerUnsupportedError(f"ticker not supported: {ticker}")
            if code == 429:
                raise MarketDataRateLimitedError("provider rate limit exceeded")
            raise MarketDataUnavailableError("provider returned an error")

        if not response.is_success:
            raise MarketDataUnavailableError(f"provider returned {response.status_code}")

        if not isinstance(payload, dict):
            raise MarketDataMalformedResponseError("provider response was not a JSON object")

        try:
            price = Decimal(str(payload["close"]))
            change = Decimal(str(payload["change"]))
            change_percent = Decimal(str(payload["percent_change"]))
            as_of = datetime.fromtimestamp(int(payload["timestamp"]), tz=timezone.utc)
        except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
            raise MarketDataMalformedResponseError(
                "provider response missing/invalid quote fields"
            ) from exc

        return MarketQuote(
            ticker=ticker,
            price=price,
            change=change,
            change_percent=change_percent,
            as_of=as_of,
            source=SOURCE,
        )

    def _log(self, ticker: str, started: float, *, status: str) -> None:
        """Minimal observability per call (ADR-0009 §22, §48-style fields).

        Never includes the API key, the full request URL/query string,
        or the raw provider payload — only the safe, fixed fields
        below.
        """
        latency_ms = (time.monotonic() - started) * 1000
        logger.info(
            "market_data_quote operation=get_quote ticker=%s source=%s status=%s latency_ms=%.1f",
            ticker,
            SOURCE,
            status,
            latency_ms,
        )
