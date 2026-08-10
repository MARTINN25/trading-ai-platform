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


@dataclass(frozen=True, slots=True)
class MarketQuote:
    """A single point-in-time quote. Never constructed with guessed/zero values."""

    ticker: str
    price: Decimal
    change: Decimal
    change_percent: Decimal
    as_of: datetime
    source: str


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
