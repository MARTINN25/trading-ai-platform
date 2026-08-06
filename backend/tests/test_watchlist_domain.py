from __future__ import annotations

import pytest

from trading_ai.watchlist.domain import (
    MAX_TICKER_LENGTH,
    InvalidTickerError,
    normalize_ticker,
)


def test_normalize_ticker_trims_and_uppercases() -> None:
    assert normalize_ticker("  aapl  ") == "AAPL"


def test_normalize_ticker_already_normalized_is_unchanged() -> None:
    assert normalize_ticker("AAPL") == "AAPL"


def test_normalize_ticker_allows_dot_and_hyphen() -> None:
    assert normalize_ticker(" brk.b ") == "BRK.B"
    assert normalize_ticker(" btc-usd ") == "BTC-USD"


def test_normalize_ticker_rejects_empty_string() -> None:
    with pytest.raises(InvalidTickerError):
        normalize_ticker("")


def test_normalize_ticker_rejects_whitespace_only_string() -> None:
    with pytest.raises(InvalidTickerError):
        normalize_ticker("   ")


def test_normalize_ticker_rejects_too_long_ticker() -> None:
    too_long = "A" * (MAX_TICKER_LENGTH + 1)

    with pytest.raises(InvalidTickerError):
        normalize_ticker(too_long)


def test_normalize_ticker_accepts_max_length_ticker() -> None:
    max_length = "A" * MAX_TICKER_LENGTH

    assert normalize_ticker(max_length) == max_length


def test_normalize_ticker_rejects_unsafe_characters() -> None:
    with pytest.raises(InvalidTickerError):
        normalize_ticker("AAPL; DROP TABLE watchlist_items;")


def test_normalize_ticker_rejects_internal_whitespace() -> None:
    with pytest.raises(InvalidTickerError):
        normalize_ticker("AA PL")
