"""AI analysis application use case.

`GenerateInstrumentAnalysis` coordinates the *existing*, already-built
instrument use cases (`GetInstrumentDetails`/`GetInstrumentPriceHistory`/
`GetInstrumentNews`) to build a bounded, provider-neutral
`InstrumentAnalysisInput`, then calls the LLM gateway once. It never
talks to Twelve Data/Finnhub/xAI SDKs directly, never opens a database
session, and never persists anything (task scope §9).

News and history are independently degradable — a failure fetching
either becomes an explicit `*_available=False` fact the model is told
about, not a fatal error (task scope §9: "quote available; news
unavailable; AI явно получает news_available=false"). The current
quote is the one required input: without it there is nothing concrete
to analyze, so its absence raises `AIInsufficientDataError` before the
LLM is ever called — this keeps a definitely-empty request from
costing a generation call.

Phase 2B (Forecast Contract, FR-006): `horizon` is now a required
argument (`AnalysisHorizon`, never silently defaulted — task scope §4)
that changes which price-history window is fetched
(`ai/horizon.py`'s `history_period_for_horizon`) and feeds the
deterministic sufficiency gate (`compute_horizon_sufficiency`) — the
gate result is threaded into `InstrumentAnalysisInput` as DATA the
model must respect and is enforced again, independently, by
`ai/gateway.py` after the model responds.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from trading_ai.ai.horizon import compute_horizon_sufficiency, history_period_for_horizon
from trading_ai.ai.types import (
    AIInsufficientDataError,
    AnalysisHorizon,
    HistorySummaryFact,
    InstrumentAnalysis,
    InstrumentAnalysisInput,
    NewsHeadlineFact,
    PriceContextFact,
)
from trading_ai.market_data.types import (
    InstrumentHistoryPeriod,
    InstrumentNews,
    InstrumentSnapshot,
    InvalidPeriodError,
    MarketDataError,
    PriceHistory,
)
from trading_ai.watchlist.domain import normalize_ticker

# Bounds the prompt independently of the news section's own UI cap of
# 10 (task scope §7: "ограничить количество news items").
_MAX_NEWS_ITEMS_FOR_PROMPT = 5
_MAX_HEADLINE_CHARS = 200
_MAX_SUMMARY_CHARS = 400


class _InstrumentDetailsUseCaseLike(Protocol):
    async def execute(self, raw_ticker: str) -> InstrumentSnapshot: ...


class _InstrumentHistoryUseCaseLike(Protocol):
    async def execute(self, raw_ticker: str, raw_period: str) -> PriceHistory: ...


class _InstrumentNewsUseCaseLike(Protocol):
    async def execute(self, raw_ticker: str) -> InstrumentNews: ...


class _AIGatewayLike(Protocol):
    async def generate_instrument_analysis(
        self, analysis_input: InstrumentAnalysisInput
    ) -> InstrumentAnalysis: ...


class GenerateInstrumentAnalysis:
    def __init__(
        self,
        details_use_case: _InstrumentDetailsUseCaseLike,
        history_use_case: _InstrumentHistoryUseCaseLike,
        news_use_case: _InstrumentNewsUseCaseLike | None,
        ai_gateway: _AIGatewayLike,
    ) -> None:
        self._details_use_case = details_use_case
        self._history_use_case = history_use_case
        # `None` when news isn't configured at all (separate provider/
        # secret from market data) — treated exactly like a failed news
        # call: degraded, not fatal (see module docstring).
        self._news_use_case = news_use_case
        self._ai_gateway = ai_gateway

    async def execute(self, raw_ticker: str, horizon: AnalysisHorizon) -> InstrumentAnalysis:
        ticker = normalize_ticker(raw_ticker)

        try:
            snapshot = await self._details_use_case.execute(ticker)
        except MarketDataError as exc:
            raise AIInsufficientDataError(
                f"quote unavailable for {ticker}; cannot generate analysis"
            ) from exc

        price_fact = _build_price_fact(snapshot)

        history_period = history_period_for_horizon(horizon)
        try:
            history = await self._history_use_case.execute(ticker, history_period.value)
        except (MarketDataError, InvalidPeriodError):
            history_fact = _unavailable_history_fact(history_period)
        else:
            history_fact = _summarize_history(history)

        if self._news_use_case is None:
            news_facts: tuple[NewsHeadlineFact, ...] = ()
            news_available = False
        else:
            try:
                news = await self._news_use_case.execute(ticker)
            except MarketDataError:
                news_facts = ()
                news_available = False
            else:
                news_facts = _build_news_facts(news)
                news_available = True

        sufficiency, sufficiency_reason = compute_horizon_sufficiency(
            horizon, history_fact, price_fact.as_of, datetime.now(timezone.utc)
        )

        analysis_input = InstrumentAnalysisInput(
            ticker=ticker,
            price=price_fact,
            history=history_fact,
            news=news_facts,
            news_available=news_available,
            horizon=horizon,
            horizon_sufficiency=sufficiency,
            horizon_sufficiency_reason=sufficiency_reason,
        )
        return await self._ai_gateway.generate_instrument_analysis(analysis_input)


def _build_price_fact(snapshot: InstrumentSnapshot) -> PriceContextFact:
    return PriceContextFact(
        ticker=snapshot.ticker,
        price=snapshot.price,
        change=snapshot.change,
        change_percent=snapshot.change_percent,
        open=snapshot.open,
        high=snapshot.high,
        low=snapshot.low,
        previous_close=snapshot.previous_close,
        volume=snapshot.volume,
        as_of=snapshot.as_of,
        quote_available=True,
    )


def _summarize_history(history: PriceHistory) -> HistorySummaryFact:
    closes = [point.close for point in history.points]
    if not closes:
        return HistorySummaryFact(
            period=history.period.value,
            first_close=None,
            last_close=None,
            min_close=None,
            max_close=None,
            points_count=0,
            history_available=False,
        )
    return HistorySummaryFact(
        period=history.period.value,
        first_close=closes[0],
        last_close=closes[-1],
        min_close=min(closes),
        max_close=max(closes),
        points_count=len(closes),
        history_available=True,
    )


def _unavailable_history_fact(period: InstrumentHistoryPeriod) -> HistorySummaryFact:
    return HistorySummaryFact(
        period=period.value,
        first_close=None,
        last_close=None,
        min_close=None,
        max_close=None,
        points_count=0,
        history_available=False,
    )


def _build_news_facts(news: InstrumentNews) -> tuple[NewsHeadlineFact, ...]:
    facts = []
    for item in news.items[:_MAX_NEWS_ITEMS_FOR_PROMPT]:
        summary = item.summary[:_MAX_SUMMARY_CHARS] if item.summary else None
        facts.append(
            NewsHeadlineFact(
                headline=item.headline[:_MAX_HEADLINE_CHARS],
                summary=summary,
                source=item.source,
                published_at=item.published_at,
            )
        )
    return tuple(facts)
