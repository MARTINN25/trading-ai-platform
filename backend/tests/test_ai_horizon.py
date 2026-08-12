"""Deterministic tests for `ai/horizon.py` (Phase 2B, task scope §22).

Every function under test is pure and network-free — no gateway, no
market/news provider, no LLM. These tests exist specifically so the
sufficiency gate/`check_after` logic is verified without ever calling
xAI (task scope §21: "Ordinary pytest must not call xAI").
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from trading_ai.ai.horizon import (
    InvalidHorizonError,
    compute_check_after,
    compute_horizon_sufficiency,
    history_period_for_horizon,
    parse_horizon,
)
from trading_ai.ai.types import AnalysisHorizon, HistorySummaryFact, HorizonDataSufficiency
from trading_ai.market_data.types import InstrumentHistoryPeriod

_T = datetime(2026, 3, 2, 14, 30, tzinfo=timezone.utc)


def _history(points_count: int, available: bool = True) -> HistorySummaryFact:
    if not available:
        return HistorySummaryFact(
            period="1M", first_close=None, last_close=None, min_close=None, max_close=None,
            points_count=0, history_available=False,
        )
    return HistorySummaryFact(
        period="1M", first_close=None, last_close=None, min_close=None, max_close=None,
        points_count=points_count, history_available=True,
    )


# --- parse_horizon ------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("short", AnalysisHorizon.SHORT),
        ("SHORT", AnalysisHorizon.SHORT),
        ("  Short  ", AnalysisHorizon.SHORT),
        ("medium", AnalysisHorizon.MEDIUM),
        ("long", AnalysisHorizon.LONG),
    ],
)
def test_parse_horizon_accepts_valid_values(raw: str, expected: AnalysisHorizon) -> None:
    assert parse_horizon(raw) == expected


@pytest.mark.parametrize("raw", ["", "scalp", "1d", "short-term", "медиум"])
def test_parse_horizon_rejects_invalid_values(raw: str) -> None:
    """FR-006: no horizon is ever silently defaulted — an empty or
    unrecognized value is always an explicit error, never a fallback."""
    with pytest.raises(InvalidHorizonError):
        parse_horizon(raw)


# --- history_period_for_horizon ------------------------------------------


def test_history_period_for_horizon_short_reuses_existing_one_month_window() -> None:
    assert history_period_for_horizon(AnalysisHorizon.SHORT) == InstrumentHistoryPeriod.ONE_MONTH


def test_history_period_for_horizon_medium_uses_three_month_window() -> None:
    assert history_period_for_horizon(AnalysisHorizon.MEDIUM) == InstrumentHistoryPeriod.THREE_MONTH


def test_history_period_for_horizon_long_uses_one_year_window() -> None:
    """FR-006: LONG must not be generated from the same 1-month window
    as SHORT — this is the deterministic guarantee that it isn't."""
    period = history_period_for_horizon(AnalysisHorizon.LONG)
    assert period == InstrumentHistoryPeriod.ONE_YEAR
    assert history_period_for_horizon(AnalysisHorizon.SHORT) != period


# --- compute_check_after --------------------------------------------------


def test_compute_check_after_short_skips_weekend() -> None:
    """`_T` is a Monday (2026-03-02) — 5 trading days later must land on
    the following Monday (2026-03-09), skipping the intervening Sat/Sun."""
    assert _T.weekday() == 0  # Monday
    check_after = compute_check_after(_T, AnalysisHorizon.SHORT)
    assert check_after.date().isoformat() == "2026-03-09"
    assert check_after.weekday() == 0


def test_compute_check_after_medium_is_eight_weeks_later() -> None:
    check_after = compute_check_after(_T, AnalysisHorizon.MEDIUM)
    assert (check_after - _T).days == 56


def test_compute_check_after_long_is_twelve_months_later() -> None:
    check_after = compute_check_after(_T, AnalysisHorizon.LONG)
    assert check_after.year == _T.year + 1
    assert check_after.month == _T.month
    assert check_after.day == _T.day


def test_compute_check_after_long_clamps_day_for_short_month() -> None:
    """Jan 31 + 12 months lands on a leap Feb 29 (or clamps to the 28th
    in a non-leap year) — never overflows into March."""
    jan_31 = datetime(2027, 1, 31, tzinfo=timezone.utc)
    check_after = compute_check_after(jan_31, AnalysisHorizon.LONG)
    assert check_after.month == 1
    assert check_after.year == 2028


def test_compute_check_after_is_always_in_the_future_relative_to_input() -> None:
    for horizon in AnalysisHorizon:
        assert compute_check_after(_T, horizon) > _T


# --- compute_horizon_sufficiency ------------------------------------------


def test_sufficiency_insufficient_when_history_unavailable() -> None:
    sufficiency, reason = compute_horizon_sufficiency(
        AnalysisHorizon.SHORT, _history(0, available=False), _T, _T
    )
    assert sufficiency is HorizonDataSufficiency.INSUFFICIENT
    assert reason != ""


def test_sufficiency_insufficient_when_below_short_floor() -> None:
    sufficiency, _reason = compute_horizon_sufficiency(AnalysisHorizon.SHORT, _history(4), _T, _T)
    assert sufficiency is HorizonDataSufficiency.INSUFFICIENT


def test_sufficiency_sufficient_at_short_floor() -> None:
    sufficiency, _reason = compute_horizon_sufficiency(AnalysisHorizon.SHORT, _history(5), _T, _T)
    assert sufficiency is HorizonDataSufficiency.SUFFICIENT


def test_sufficiency_insufficient_when_below_medium_floor() -> None:
    sufficiency, _reason = compute_horizon_sufficiency(AnalysisHorizon.MEDIUM, _history(19), _T, _T)
    assert sufficiency is HorizonDataSufficiency.INSUFFICIENT


def test_sufficiency_sufficient_at_medium_floor() -> None:
    sufficiency, _reason = compute_horizon_sufficiency(AnalysisHorizon.MEDIUM, _history(20), _T, _T)
    assert sufficiency is HorizonDataSufficiency.SUFFICIENT


def test_sufficiency_insufficient_when_below_long_floor() -> None:
    """FR-006 (verbatim): LONG must not be generated confidently from
    only one month of price history — 22 points (~1 month) is well
    under the LONG floor."""
    sufficiency, reason = compute_horizon_sufficiency(AnalysisHorizon.LONG, _history(22), _T, _T)
    assert sufficiency is HorizonDataSufficiency.INSUFFICIENT
    assert "22" in reason


def test_sufficiency_sufficient_at_long_floor() -> None:
    sufficiency, _reason = compute_horizon_sufficiency(AnalysisHorizon.LONG, _history(60), _T, _T)
    assert sufficiency is HorizonDataSufficiency.SUFFICIENT


def test_sufficiency_insufficient_when_quote_stale_for_short() -> None:
    stale_as_of = _T
    now = datetime(2026, 3, 10, 14, 30, tzinfo=timezone.utc)  # 8 days later
    sufficiency, reason = compute_horizon_sufficiency(AnalysisHorizon.SHORT, _history(22), stale_as_of, now)
    assert sufficiency is HorizonDataSufficiency.INSUFFICIENT
    assert "устарела" in reason


def test_sufficiency_insufficient_when_quote_as_of_missing() -> None:
    sufficiency, _reason = compute_horizon_sufficiency(AnalysisHorizon.SHORT, _history(22), None, _T)
    assert sufficiency is HorizonDataSufficiency.INSUFFICIENT


def test_sufficiency_fresh_quote_sufficient_for_long_horizon_with_enough_history() -> None:
    """A quote a week old is fine for LONG even though it would be
    stale for SHORT — the staleness bound is horizon-relative."""
    as_of = _T
    now = datetime(2026, 3, 10, 14, 30, tzinfo=timezone.utc)  # 8 days later
    sufficiency, _reason = compute_horizon_sufficiency(AnalysisHorizon.LONG, _history(200), as_of, now)
    assert sufficiency is HorizonDataSufficiency.SUFFICIENT
