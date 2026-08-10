"""Market-data domain types — provider-neutral.

Mirrors the `llm_gateway` boundary pattern from ADR-0007 §20–21 at a
much smaller scale: callers (the watchlist application layer) depend
on this contract, never on a provider SDK/HTTP client. The only
concrete implementation wired up today (`gateway.py`) talks to Twelve
Data — an implementation choice for this vertical slice, not an
ADR-level commitment (see README). Swapping providers means writing a
new class satisfying `get_quote(ticker) -> MarketQuote`, not changing
this contract.

Market data is read-only display information for the watchlist UI —
it is never persisted (`watchlist_items` has no price columns) and is
never a source of truth for `watchlist` itself (ADR-0004 §25: only a
UNIQUE/PK-backed row is authoritative).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


@dataclass(frozen=True, slots=True)
class MarketQuote:
    """A single point-in-time quote. Never constructed with guessed/zero values."""

    ticker: str
    price: Decimal
    change: Decimal
    change_percent: Decimal
    as_of: datetime
    source: str


@dataclass(frozen=True, slots=True)
class InstrumentSnapshot:
    """A richer, point-in-time snapshot for the instrument details page.

    Same core fields as `MarketQuote` (ticker/price/change/
    change_percent/as_of/source) plus open/high/low/previous_close/
    volume — Twelve Data's `/quote` response already includes these
    (confirmed against the documented contract), so no second endpoint
    call is needed. Each optional field is `None`, never a guessed `0`,
    when the provider's response didn't include or couldn't parse it
    (see `gateway._optional_decimal`/`_optional_int`) — a missing value
    must never be displayed as if it were real data.
    """

    ticker: str
    price: Decimal
    change: Decimal
    change_percent: Decimal
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    previous_close: Decimal | None
    volume: int | None
    as_of: datetime
    source: str


@dataclass(frozen=True, slots=True)
class PricePoint:
    """One OHLCV bar for the instrument price-history chart.

    The provider layer keeps the full OHLCV shape even though today's
    line chart only needs `close` — deciding what actually crosses the
    wire is the API layer's job (task scope: don't carry fields "for
    the future" into the HTTP response). `open`/`high`/`low`/`volume`
    are `None`, not a guessed `0`, whenever Twelve Data's response
    didn't include or couldn't parse them. `close` is required — a bar
    without a usable close price is not a valid bar, and the whole
    history call fails instead of silently dropping it.
    """

    timestamp: datetime
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal
    volume: int | None


class InstrumentHistoryPeriod(Enum):
    """Application-level chart period contract.

    Frontend and API only ever see these three fixed values — never a
    raw Twelve Data `interval`/`outputsize` pair (task scope §3).
    `gateway.py` is the only place that maps a period to
    provider-specific request parameters.
    """

    ONE_DAY = "1D"
    FIVE_DAY = "5D"
    ONE_MONTH = "1M"


@dataclass(frozen=True, slots=True)
class PriceHistory:
    """A requested period's bars for one ticker, already ASC-sorted and provider-neutral."""

    ticker: str
    period: InstrumentHistoryPeriod
    source: str
    points: tuple[PricePoint, ...]


class InvalidPeriodError(Exception):
    """Raised when a requested chart period isn't one of `InstrumentHistoryPeriod`.

    A request-validation error, not a provider-call failure — mirrors
    `trading_ai.watchlist.domain.InvalidTickerError` (mapped to `422`
    by the API layer), not `MarketDataError` (mapped to `404`/`503`/
    `504` — those only happen after a provider call is actually made).
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def normalize_period(raw: str) -> InstrumentHistoryPeriod:
    """Parse/validate a raw query-param string into `InstrumentHistoryPeriod`.

    Raises `InvalidPeriodError` for anything else — never silently
    falls back to a default period.
    """
    try:
        return InstrumentHistoryPeriod(raw)
    except ValueError as exc:
        allowed = ", ".join(period.value for period in InstrumentHistoryPeriod)
        raise InvalidPeriodError(f"period must be one of: {allowed}") from exc


class MarketDataError(Exception):
    """Base class for market-data gateway errors.

    Never an `HTTPException` — this is the domain/application-facing
    error taxonomy (mirrors ADR-0007 §39); the API layer maps these to
    HTTP (ADR-0002 §17), the same way `DuplicateTickerError` etc. are
    mapped for watchlist.
    """


class MarketDataUnavailableError(MarketDataError):
    """Provider unreachable, returned a server error, or an unexpected error shape."""


class MarketDataTimeoutError(MarketDataError):
    """The bounded provider request timeout was exceeded."""


class MarketDataRateLimitedError(MarketDataError):
    """Provider signaled rate limiting (e.g. HTTP 429)."""


class TickerUnsupportedError(MarketDataError):
    """Provider does not recognize/support this ticker."""


class MarketDataMalformedResponseError(MarketDataError):
    """Provider responded, but the payload didn't match the expected shape."""
