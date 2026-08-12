"""Deterministic horizon logic for Forecast Contract (Phase 2B, FR-006).

Everything here is pure and network-free, same discipline as
`news_intelligence/preprocessing.py` (ENGINEERING_PRINCIPLES.md points
54-55: deterministic work happens in code, not by asking the model).
Three independent, narrow responsibilities, each directly testable
without any LLM call:

1. `parse_horizon` — validate the user's explicit horizon choice
   (FR-006: never silently defaulted).
2. `history_period_for_horizon` — map a horizon to the evidence window
   `ai/use_cases.py` fetches (task scope §11) — reuses
   `market_data.types.InstrumentHistoryPeriod`, no new provider
   capability invented.
3. `compute_check_after` — `generated_at` + horizon semantics
   (task scope §13), never left to the model to invent.
4. `compute_horizon_sufficiency` — the deterministic precondition gate
   (task scope §12): decides whether the *collected* evidence window
   actually supports the *requested* horizon, independent of whatever
   the model itself later claims.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trading_ai.ai.types import AnalysisHorizon, HistorySummaryFact, HorizonDataSufficiency
from trading_ai.market_data.types import InstrumentHistoryPeriod

_HORIZON_VALUES = {horizon.value: horizon for horizon in AnalysisHorizon}


class InvalidHorizonError(Exception):
    """Raised when a requested horizon isn't one of `AnalysisHorizon`.

    A request-validation error, not a data/provider-call failure —
    mirrors `market_data.types.InvalidPeriodError` (mapped to `422` by
    the API layer), not a `MarketDataError`/`AIAnalysisError` subtype.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def parse_horizon(raw: str) -> AnalysisHorizon:
    """Parse/validate a raw query-param string into `AnalysisHorizon`.

    Raises `InvalidHorizonError` for anything else, including an empty
    string — there is no default horizon (FR-006: "не подставлять
    горизонт по умолчанию, если API/документы требуют явного выбора
    пользователя"). Case-insensitive purely as user-input leniency
    (`"SHORT"`/`"short"` both valid) — the wire value stored/logged is
    always the canonical lowercase `AnalysisHorizon.value`.
    """
    horizon = _HORIZON_VALUES.get(raw.strip().lower())
    if horizon is None:
        allowed = ", ".join(sorted(_HORIZON_VALUES))
        raise InvalidHorizonError(f"horizon must be one of: {allowed}")
    return horizon


# Task scope §11: the existing fixed 1-month window used for every
# analysis before this task is kept for SHORT (1-5 trading days needs
# fresh daily/intraday data and recent news, not months of lookback —
# `FORECAST_CONTRACT.md` §7 table). MEDIUM/LONG get wider windows
# (`market_data/gateway.py`'s `_PERIOD_PROVIDER_PARAMS`) — see that
# module for the exact provider request sizing and the documented
# reasoning for each.
_HISTORY_PERIOD_BY_HORIZON: dict[AnalysisHorizon, InstrumentHistoryPeriod] = {
    AnalysisHorizon.SHORT: InstrumentHistoryPeriod.ONE_MONTH,
    AnalysisHorizon.MEDIUM: InstrumentHistoryPeriod.THREE_MONTH,
    AnalysisHorizon.LONG: InstrumentHistoryPeriod.ONE_YEAR,
}


def history_period_for_horizon(horizon: AnalysisHorizon) -> InstrumentHistoryPeriod:
    return _HISTORY_PERIOD_BY_HORIZON[horizon]


def _add_months(value: datetime, months: int) -> datetime:
    """Stdlib-only calendar-month addition (no new dependency —
    ENGINEERING_PRINCIPLES.md point 67). Clamps the day-of-month to the
    target month's actual length (e.g. Jan 31 + 1 month -> Feb 28/29),
    same rule most calendar libraries use for this ambiguous case."""
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, _days_in_month(year, month))
    return value.replace(year=year, month=month, day=day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        next_month_start = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month_start = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    this_month_start = datetime(year, month, 1, tzinfo=timezone.utc)
    return (next_month_start - this_month_start).days


def _add_trading_days(value: datetime, trading_days: int) -> datetime:
    """Skips Saturday/Sunday only — no market-holiday calendar (task
    scope §13: "уважать рыночно-сессионную семантику насколько
    позволяет текущая поддержка акций", documented limitation, not a
    full trading calendar — `ADR-0012` §22 leaves full session-calendar
    awareness to a future background-monitoring runtime, not this
    synchronous request path)."""
    remaining = trading_days
    current = value
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Monday=0 .. Sunday=6
            remaining -= 1
    return current


# Deterministic, from `generated_at` + horizon semantics only (task
# scope §13) — never a value the model is asked to produce. Uses the
# *upper* bound of each approved range (FR-006): re-checking a thesis
# once its full stated window has plausibly played out is a more
# conservative, defensible default than the lower bound, and is a
# single, documented implementation choice rather than something
# invented per-call.
_SHORT_CHECK_AFTER_TRADING_DAYS = 5
_MEDIUM_CHECK_AFTER_WEEKS = 8
_LONG_CHECK_AFTER_MONTHS = 12


def compute_check_after(generated_at: datetime, horizon: AnalysisHorizon) -> datetime:
    if horizon is AnalysisHorizon.SHORT:
        return _add_trading_days(generated_at, _SHORT_CHECK_AFTER_TRADING_DAYS)
    if horizon is AnalysisHorizon.MEDIUM:
        return generated_at + timedelta(weeks=_MEDIUM_CHECK_AFTER_WEEKS)
    return _add_months(generated_at, _LONG_CHECK_AFTER_MONTHS)


# Minimum daily-bar point counts per horizon (task scope §12: "если
# точный минимум не может быть обоснован, использовать architecture-
# consistent качественный sufficiency gate и явно задокументировать
# его" — FORECAST_CONTRACT.md §7 explicitly leaves the exact number to
# Solution Architect implementation judgment, not a Product-Owner-fixed
# threshold). These are that documented judgment call, not a claim of
# a scientifically derived minimum:
# - SHORT: >=5 (about one trading week) — the horizon itself is only
#   1-5 trading days out, so a full quarter of lookback is not the
#   point; a firm floor still rules out a single-point "trend".
# - MEDIUM: >=20 (about one calendar month of daily bars) — meaningful
#   lookback for a view that extends up to ~8 weeks out.
# - LONG: >=60 (about one calendar quarter of daily bars) — deliberately
#   less than the full ~252-point fetch window (`market_data/gateway.py`),
#   but far more than "one month of history" (FR-006's explicit,
#   verbatim prohibition) — a newly listed instrument with less than a
#   quarter of trading history cannot honestly support a 2-12 month view.
_MIN_HISTORY_POINTS_BY_HORIZON: dict[AnalysisHorizon, int] = {
    AnalysisHorizon.SHORT: 5,
    AnalysisHorizon.MEDIUM: 20,
    AnalysisHorizon.LONG: 60,
}

# Quote staleness bound per horizon (task scope §12 example: "stale
# required inputs") — a SHORT view leans on the input being close to
# real-time far more than a LONG one does. Same "documented judgment
# call, not an invented false-precision number" caveat as above.
_MAX_QUOTE_AGE_BY_HORIZON: dict[AnalysisHorizon, timedelta] = {
    AnalysisHorizon.SHORT: timedelta(days=3),
    AnalysisHorizon.MEDIUM: timedelta(days=7),
    AnalysisHorizon.LONG: timedelta(days=14),
}


def compute_horizon_sufficiency(
    horizon: AnalysisHorizon,
    history: HistorySummaryFact,
    quote_as_of: datetime | None,
    now: datetime,
) -> tuple[HorizonDataSufficiency, str]:
    """The deterministic precondition gate (task scope §12) — computed
    *before* the LLM call, passed to the model as DATA, and enforced
    again *after* the LLM call by `ai/gateway.py` (belt-and-suspenders:
    the model is never the sole authority on the `INSUFFICIENT`
    direction). Returns a short, Russian, human-readable reason
    suitable for surfacing as `InstrumentAnalysis.uncertainty` when the
    result is downgraded.
    """
    if not history.history_available or history.points_count == 0:
        return (
            HorizonDataSufficiency.INSUFFICIENT,
            "История цены недоступна — недостаточно данных для горизонта "
            f"{horizon.value}.",
        )

    min_points = _MIN_HISTORY_POINTS_BY_HORIZON[horizon]
    if history.points_count < min_points:
        return (
            HorizonDataSufficiency.INSUFFICIENT,
            f"Доступно только {history.points_count} точек истории цены — "
            f"недостаточно для честной поддержки горизонта {horizon.value} "
            f"(нужно от {min_points}).",
        )

    if quote_as_of is None:
        return (
            HorizonDataSufficiency.INSUFFICIENT,
            "Момент актуальности котировки неизвестен.",
        )

    max_age = _MAX_QUOTE_AGE_BY_HORIZON[horizon]
    age = now - quote_as_of
    if age > max_age:
        return (
            HorizonDataSufficiency.INSUFFICIENT,
            f"Котировка устарела ({age.days} дн.) для горизонта {horizon.value}.",
        )

    return (HorizonDataSufficiency.SUFFICIENT, "")
