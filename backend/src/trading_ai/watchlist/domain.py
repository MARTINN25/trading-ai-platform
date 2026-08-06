"""Watchlist domain model.

Deliberately not the SQLAlchemy model (`trading_ai.watchlist.models`):
`WatchlistItem` is a plain, immutable value object with no dependency
on the ORM, so domain rules stay testable without a database and the
API layer never has to return a raw ORM instance (ADR-0002, §18.2).

Ticker normalization/validation lives here, not in the transport DTO
or the repository — transport validation does not replace business
validation (ADR-0002, §18.2), and the repository only persists an
already-valid ticker.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

# Generous but bounded: covers plain equity tickers (AAPL), dotted/dashed
# share classes (BRK.B, BF-B) and crypto pairs (BTC-USD) without
# inventing exchange-specific validation rules.
MAX_TICKER_LENGTH = 15

# Uppercase letters, digits, dot and hyphen: predictable and safe (no
# whitespace/control characters), without guessing a real exchange's
# symbol grammar.
_TICKER_PATTERN = re.compile(r"^[A-Z0-9.\-]+$")


class WatchlistError(Exception):
    """Base class for watchlist domain/application errors."""


class InvalidTickerError(WatchlistError):
    """Raised when a ticker fails normalization/validation."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class DuplicateTickerError(WatchlistError):
    """Raised when a ticker already exists in the watchlist."""

    def __init__(self, ticker: str) -> None:
        super().__init__(f"ticker already in watchlist: {ticker}")
        self.ticker = ticker


def normalize_ticker(raw: str) -> str:
    """Trim, uppercase, and validate a raw ticker string.

    Raises `InvalidTickerError` for anything that is not a short,
    predictable, database-safe symbol.
    """
    ticker = raw.strip().upper()
    if not ticker:
        raise InvalidTickerError("ticker must not be empty")
    if len(ticker) > MAX_TICKER_LENGTH:
        raise InvalidTickerError(
            f"ticker must be at most {MAX_TICKER_LENGTH} characters"
        )
    if not _TICKER_PATTERN.match(ticker):
        raise InvalidTickerError(
            "ticker must contain only letters, digits, '.' or '-'"
        )
    return ticker


@dataclass(frozen=True, slots=True)
class WatchlistItem:
    """Immutable watchlist entry — the domain/application-facing shape."""

    id: int
    ticker: str
    created_at: datetime
