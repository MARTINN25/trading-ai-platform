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
    InstrumentHistoryPeriod,
    InstrumentSearchResult,
    InstrumentSnapshot,
    MarketDataError,
    MarketDataMalformedResponseError,
    MarketDataRateLimitedError,
    MarketDataTimeoutError,
    MarketDataUnavailableError,
    MarketQuote,
    PriceHistory,
    PricePoint,
    TickerUnsupportedError,
)

logger = logging.getLogger(__name__)

SOURCE = "twelvedata"
_BASE_URL = "https://api.twelvedata.com"

# Bounded, single attempt — no automatic retry (task scope: "не делать
# бесконечные retry"). A user-visible "Обновить данные" action is the
# retry mechanism, not this gateway.
_REQUEST_TIMEOUT_SECONDS = 5.0

# Application period -> Twelve Data `/time_series` (interval, outputsize).
# One provider request per chart load (task scope §6) — never a
# request per point. Confirmed live against the account's actual plan
# before picking these (see README): `5min`/`1h`/`1day` intervals and
# `timezone=UTC`/`order=asc` all work on the current free tier.
#
# - 1D -> 5min bars, outputsize 100: covers a full ~6.5h NYSE session
#   (~78 bars) with headroom; intentionally *not* clipped to the
#   current calendar day — "last ~100 5-minute bars" is a simpler and
#   equally valid reading of "1D" than a strict midnight boundary.
# - 5D -> 1h bars, outputsize 40: ~7 hourly bars/session * 5 sessions,
#   with headroom for holidays/partial sessions.
# - 1M -> 1day bars, outputsize 25: a calendar month is ~21-23 trading
#   days; headroom covers holidays.
# - 3M -> 1day bars, outputsize 70 (Phase 2B, task scope §11): ~63
#   trading days in a calendar quarter; headroom covers holidays. Added
#   for horizon-aware analysis evidence windows (`ai/horizon.py`), not
#   exposed as a chart-UI option — MEDIUM's approved upper bound is ~8
#   weeks (`FUNCTIONAL_REQUIREMENTS.md` FR-006), so this window gives
#   comfortable lookback headroom above that bound rather than cutting
#   it exactly at 8 weeks.
# - 1Y -> 1day bars, outputsize 260 (Phase 2B): ~252 trading days in a
#   calendar year; headroom covers holidays. Used for LONG (~2-12
#   months) — a full calendar year of daily bars is a deliberate,
#   documented implementation judgment call (`FORECAST_CONTRACT.md` §7
#   explicitly leaves the exact minimum window to Solution Architect
#   judgment, not a Product-Owner-fixed number), chosen to be
#   meaningfully wider than what a 1-month window could honestly
#   support, per the Product Owner's explicit "not from one month of
#   history" requirement (FR-006) — not a claim that exactly 252 points
#   is the correct minimum for every LONG case; `ai/horizon.py`'s
#   sufficiency gate is the actual enforcement point, this window is
#   only the fetch request.
_PERIOD_PROVIDER_PARAMS: dict[InstrumentHistoryPeriod, tuple[str, int]] = {
    InstrumentHistoryPeriod.ONE_DAY: ("5min", 100),
    InstrumentHistoryPeriod.FIVE_DAY: ("1h", 40),
    InstrumentHistoryPeriod.ONE_MONTH: ("1day", 25),
    InstrumentHistoryPeriod.THREE_MONTH: ("1day", 70),
    InstrumentHistoryPeriod.ONE_YEAR: ("1day", 260),
}

# Final cap on what's returned to the caller (task scope §6: "максимум
# 10 результатов"), applied *after* the US-common-stock filter below —
# no longer the same number requested from the provider (see
# `_SEARCH_PROVIDER_OUTPUT_SIZE`).
_SEARCH_RESULT_LIMIT = 10

# Requested `outputsize` — the documented max (confirmed live: 1
# credit/request regardless of `outputsize`, no extra cost). MVP scope
# is US-listed common stock only (Product Owner decision, R2): a
# same-company match on a US exchange is frequently *not* among the
# provider's first ~10 results for a name search — confirmed live for
# "Microsoft" (NASDAQ:MSFT was the 22nd of 107 raw matches at
# `outputsize=120`, past the point a 10-item request would ever have
# reached) and even for an exact-ticker "MSFT" query (NASDAQ:MSFT was
# the 2nd of several same-ticker cross-exchange matches). Requesting
# the max and filtering the response is the only reliable way to
# surface it, since `/symbol_search` has no request-time country/
# exchange/instrument_type filter (confirmed against the official
# docs — only `symbol`, `outputsize`, `show_plan` are documented
# parameters).
_SEARCH_PROVIDER_OUTPUT_SIZE = 120


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
            response = await self._fetch_raw(ticker)
            quote = self._parse_quote(ticker, response)
        except MarketDataError as exc:
            self._log(ticker, started, operation="get_quote", status=type(exc).__name__)
            raise
        self._log(ticker, started, operation="get_quote", status="ok")
        return quote

    async def get_instrument_snapshot(self, ticker: str) -> InstrumentSnapshot:
        started = time.monotonic()
        try:
            response = await self._fetch_raw(ticker)
            snapshot = self._parse_snapshot(ticker, response)
        except MarketDataError as exc:
            self._log(
                ticker, started, operation="get_instrument_details", status=type(exc).__name__
            )
            raise
        self._log(ticker, started, operation="get_instrument_details", status="ok")
        return snapshot

    async def get_price_history(
        self, ticker: str, period: InstrumentHistoryPeriod
    ) -> PriceHistory:
        started = time.monotonic()
        try:
            response = await self._fetch_history_raw(ticker, period)
            points = self._parse_history(ticker, response)
        except MarketDataError as exc:
            self._log_history(ticker, period, started, status=type(exc).__name__)
            raise
        self._log_history(ticker, period, started, status="ok", points_count=len(points))
        return PriceHistory(ticker=ticker, period=period, source=SOURCE, points=tuple(points))

    async def search_instruments(self, query: str) -> list[InstrumentSearchResult]:
        started = time.monotonic()
        try:
            response = await self._get(
                "/symbol_search", {"symbol": query, "outputsize": _SEARCH_PROVIDER_OUTPUT_SIZE}
            )
            results = self._parse_search(query, response)
        except MarketDataError as exc:
            self._log_search(query, started, status=type(exc).__name__)
            raise
        self._log_search(query, started, status="ok", result_count=len(results))
        return results

    async def _fetch_raw(self, ticker: str) -> httpx.Response:
        return await self._get("/quote", {"symbol": ticker})

    async def _fetch_history_raw(
        self, ticker: str, period: InstrumentHistoryPeriod
    ) -> httpx.Response:
        interval, outputsize = _PERIOD_PROVIDER_PARAMS[period]
        return await self._get(
            "/time_series",
            {
                "symbol": ticker,
                "interval": interval,
                "outputsize": outputsize,
                # Requested as a hint to reduce provider-side work, but
                # never trusted — `_parse_history` sorts defensively
                # regardless of what the provider actually returns.
                "order": "asc",
                # Avoids needing to know the exchange's local
                # timezone/DST rules ourselves to build a timezone-aware
                # `datetime` — the provider does that normalization.
                "timezone": "UTC",
            },
        )

    async def _get(self, path: str, params: dict[str, Any]) -> httpx.Response:
        try:
            async with httpx.AsyncClient(
                timeout=_REQUEST_TIMEOUT_SECONDS, transport=self._transport
            ) as client:
                response = await client.get(
                    f"{self._base_url}{path}",
                    params=params,
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
            raise MarketDataTimeoutError(f"timeout fetching {path}") from exc
        except httpx.HTTPError as exc:
            # Network-level failure (connection refused/reset/DNS/etc).
            # Never includes the request URL/headers (which carry the
            # API key) in the raised message.
            raise MarketDataUnavailableError(f"network error fetching {path}") from exc

        return response

    def _validate_payload(self, ticker: str, response: httpx.Response) -> dict[str, Any]:
        """Status/shape checks shared by quote and snapshot parsing.

        Returns the decoded JSON object on success, or raises the same
        `MarketDataError` subclass regardless of which parse path
        called it — the two only diverge on which fields they then
        extract from that object.
        """
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

        return payload

    def _parse_quote(self, ticker: str, response: httpx.Response) -> MarketQuote:
        payload = self._validate_payload(ticker, response)

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

    def _parse_snapshot(self, ticker: str, response: httpx.Response) -> InstrumentSnapshot:
        payload = self._validate_payload(ticker, response)

        # Core fields: same as `_parse_quote` — missing/invalid here
        # means the response can't be trusted at all, so the whole
        # call fails the same way `get_quote` already does.
        try:
            price = Decimal(str(payload["close"]))
            change = Decimal(str(payload["change"]))
            change_percent = Decimal(str(payload["percent_change"]))
            as_of = datetime.fromtimestamp(int(payload["timestamp"]), tz=timezone.utc)
        except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
            raise MarketDataMalformedResponseError(
                "provider response missing/invalid quote fields"
            ) from exc

        # Supplementary display fields: absent or unparseable becomes
        # `None` ("Данные недоступны" in the UI), not a failed request
        # and never a guessed `0` — the task scope explicitly forbids
        # inventing values the provider didn't actually give us.
        return InstrumentSnapshot(
            ticker=ticker,
            price=price,
            change=change,
            change_percent=change_percent,
            open=_optional_decimal(payload.get("open")),
            high=_optional_decimal(payload.get("high")),
            low=_optional_decimal(payload.get("low")),
            previous_close=_optional_decimal(payload.get("previous_close")),
            volume=_optional_int(payload.get("volume")),
            as_of=as_of,
            source=SOURCE,
        )

    def _parse_history(self, ticker: str, response: httpx.Response) -> list[PricePoint]:
        # `_validate_payload` doesn't care that this is a /time_series
        # response rather than /quote — status-code mapping and the
        # `{"status": "error"}` body shape are identical across both
        # endpoints (confirmed against the docs).
        payload = self._validate_payload(ticker, response)

        values = payload.get("values")
        if not isinstance(values, list):
            raise MarketDataMalformedResponseError("provider response missing values list")

        points: list[PricePoint] = []
        for raw_point in values:
            if not isinstance(raw_point, dict):
                raise MarketDataMalformedResponseError(
                    "provider response contained a non-object point"
                )
            try:
                point_timestamp = _parse_history_timestamp(raw_point["datetime"])
                close = Decimal(str(raw_point["close"]))
            except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
                raise MarketDataMalformedResponseError(
                    "provider response missing/invalid point fields"
                ) from exc

            points.append(
                PricePoint(
                    timestamp=point_timestamp,
                    open=_optional_decimal(raw_point.get("open")),
                    high=_optional_decimal(raw_point.get("high")),
                    low=_optional_decimal(raw_point.get("low")),
                    close=close,
                    volume=_optional_int(raw_point.get("volume")),
                )
            )

        # Defensive, not just a request hint: never trust the
        # provider's actual ordering, even though `order=asc` was
        # requested (task scope §11 regression case).
        points.sort(key=lambda point: point.timestamp)
        return points

    def _parse_search(self, query: str, response: httpx.Response) -> list[InstrumentSearchResult]:
        # `_validate_payload` doesn't care that this is a /symbol_search
        # response — status-code mapping and the `{"status": "error"}`
        # body shape are identical across Twelve Data endpoints
        # (confirmed against the docs, same as history/quote).
        payload = self._validate_payload(query, response)

        data = payload.get("data")
        if not isinstance(data, list):
            raise MarketDataMalformedResponseError("provider response missing data list")

        results: list[InstrumentSearchResult] = []
        for raw_item in data:
            # MVP scope filter first, on the *raw* item (Product Owner
            # decision, R2) — `country`/`instrument_type` aren't carried
            # into `InstrumentSearchResult` (provider-neutral contract,
            # no UI need), so this has to happen before mapping away.
            if not _is_us_common_stock(raw_item):
                continue
            result = _parse_search_item(raw_item)
            if result is not None:
                results.append(result)

        results = _dedupe_by_ticker(results)
        results = _rank_exact_ticker_match_first(query, results)

        # Defensive re-cap, independent of the requested `outputsize`
        # (same "never fully trust the provider" rule as history/news).
        return results[:_SEARCH_RESULT_LIMIT]

    def _log_search(
        self, query: str, started: float, *, status: str, result_count: int | None = None
    ) -> None:
        """Same rules as `_log`: no API key, no URL, no raw payload —
        and never the full user query text either (task scope §15),
        only its length.
        """
        latency_ms = (time.monotonic() - started) * 1000
        query_length = len(query)
        if result_count is None:
            logger.info(
                "market_data_search operation=search_instruments query_length=%d source=%s "
                "status=%s latency_ms=%.1f",
                query_length,
                SOURCE,
                status,
                latency_ms,
            )
        else:
            logger.info(
                "market_data_search operation=search_instruments query_length=%d source=%s "
                "status=%s latency_ms=%.1f result_count=%d",
                query_length,
                SOURCE,
                status,
                latency_ms,
                result_count,
            )

    def _log(self, ticker: str, started: float, *, operation: str, status: str) -> None:
        """Minimal observability per call (ADR-0009 §22, §48-style fields).

        Never includes the API key, the full request URL/query string,
        or the raw provider payload — only the safe, fixed fields
        below.
        """
        latency_ms = (time.monotonic() - started) * 1000
        logger.info(
            "market_data_quote operation=%s ticker=%s source=%s status=%s latency_ms=%.1f",
            operation,
            ticker,
            SOURCE,
            status,
            latency_ms,
        )

    def _log_history(
        self,
        ticker: str,
        period: InstrumentHistoryPeriod,
        started: float,
        *,
        status: str,
        points_count: int | None = None,
    ) -> None:
        """Same rules as `_log`: no API key, no URL, no raw payload.

        `points_count` is included only on success (task scope §15) —
        a failed call has no point count to report.
        """
        latency_ms = (time.monotonic() - started) * 1000
        if points_count is None:
            logger.info(
                "market_data_history operation=get_price_history ticker=%s period=%s "
                "source=%s status=%s latency_ms=%.1f",
                ticker,
                period.value,
                SOURCE,
                status,
                latency_ms,
            )
        else:
            logger.info(
                "market_data_history operation=get_price_history ticker=%s period=%s "
                "source=%s status=%s latency_ms=%.1f points_count=%d",
                ticker,
                period.value,
                SOURCE,
                status,
                latency_ms,
                points_count,
            )


def _parse_history_timestamp(value: str) -> datetime:
    """Twelve Data returns `"YYYY-MM-DD HH:MM:SS"` for intraday
    intervals and `"YYYY-MM-DD"` for daily/weekly/monthly ones — both
    already normalized to UTC wall-clock time because the request
    passes `timezone=UTC` (see `_fetch_history_raw`), so both are
    attached `tzinfo=UTC` directly rather than guessed/converted.
    """
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"unrecognized provider datetime format: {value!r}")


def _parse_search_item(raw: Any) -> InstrumentSearchResult | None:
    """Best-effort per-item parse.

    Returns `None` (skip this one item) rather than failing the whole
    search — one malformed match must never take down an otherwise-good
    result list (same defensive-skip policy as
    `news_gateway._parse_news_item`).
    """
    if not isinstance(raw, dict):
        return None
    ticker = raw.get("symbol")
    name = raw.get("instrument_name")
    if not isinstance(ticker, str) or not ticker.strip():
        return None
    if not isinstance(name, str) or not name.strip():
        return None
    return InstrumentSearchResult(
        ticker=ticker.strip(),
        name=name.strip(),
        exchange=_optional_str(raw.get("exchange")),
        instrument_type=_optional_str(raw.get("instrument_type")),
        currency=_optional_str(raw.get("currency")),
    )


def _is_us_common_stock(raw: Any) -> bool:
    """MVP instrument universe: US-listed common stock only (Product
    Owner decision, R2 — see README "Instrument search" for the full
    write-up).

    An exact-string match on two fields Twelve Data's own docs define
    precisely — `country` ("country to which stock exchange belongs
    to") and `instrument_type` — not a guessed exchange/MIC-code
    mapping. `/symbol_search` has no request-time filter for either
    (confirmed against the official docs: only `symbol`, `outputsize`,
    `show_plan` are documented parameters), so this filters the
    response instead.
    """
    if not isinstance(raw, dict):
        return False
    return raw.get("country") == "United States" and raw.get("instrument_type") == "Common Stock"


def _dedupe_by_ticker(results: list[InstrumentSearchResult]) -> list[InstrumentSearchResult]:
    """Collapse same-ticker matches from different exchanges to one entry.

    The watchlist's persisted identity is the ticker string alone — no
    exchange column, `UNIQUE(ticker)` (`watchlist/models.py`). Kept as
    a defensive safety net after `_is_us_common_stock` narrows the
    result set: the filter is expected to leave at most one US common-
    stock match per ticker, but this guarantees it regardless (keeps
    the first, highest-ranked, per provider order).
    """
    seen: set[str] = set()
    deduped: list[InstrumentSearchResult] = []
    for result in results:
        key = result.ticker.upper()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(result)
    return deduped


def _rank_exact_ticker_match_first(
    query: str, results: list[InstrumentSearchResult]
) -> list[InstrumentSearchResult]:
    """Move an exact ticker match to the front; stable otherwise.

    Generic search relevance (matching the literal query string) on
    top of the already-filtered US-common-stock result set — this
    function itself still doesn't know about exchange/country/
    instrument_type, that's `_is_us_common_stock`'s job. Confirmed live
    (R2): even querying the exact ticker "MSFT" returns several
    same-ticker cross-exchange matches from the provider (Argentina,
    Mexico, Peru, Poland, Austria...) before `_is_us_common_stock`
    narrows it down — this ranking is a secondary safety net, not the
    primary mechanism.
    """
    normalized_query = query.strip().upper()
    exact = [result for result in results if result.ticker.upper() == normalized_query]
    rest = [result for result in results if result.ticker.upper() != normalized_query]
    return exact + rest


def _optional_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
