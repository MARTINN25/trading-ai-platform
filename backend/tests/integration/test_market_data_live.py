"""Opt-in smoke test against the real Twelve Data API.

Deliberately its own file with only `@pytest.mark.live_provider` on the
one test — never the module-level `pytestmark = pytest.mark.integration`
used by `test_watchlist_integration.py`. If this file carried that
marker too, a plain `pytest -m integration` run would also fire a real
external HTTP call, which the task explicitly rules out ("не делать
live external-provider tests частью обычного pytest suite").

Run explicitly:

    TRADING_AI_LIVE_MARKET_DATA_API_KEY=... \\
        python -m pytest -m live_provider tests/integration -v
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from trading_ai.ai.gateway import XAIGateway
from trading_ai.ai.types import (
    AnalysisHorizon,
    HistorySummaryFact,
    HorizonDataSufficiency,
    InstrumentAnalysisInput,
    PriceContextFact,
)
from trading_ai.market_data.gateway import TwelveDataGateway
from trading_ai.market_data.news_gateway import FinnhubNewsGateway
from trading_ai.market_data.types import InstrumentHistoryPeriod

_LIVE_API_KEY = os.environ.get("TRADING_AI_LIVE_MARKET_DATA_API_KEY")
_LIVE_NEWS_API_KEY = os.environ.get("TRADING_AI_LIVE_NEWS_API_KEY")
_LIVE_LLM_API_KEY = os.environ.get("TRADING_AI_LIVE_LLM_API_KEY")


@pytest.mark.live_provider
@pytest.mark.skipif(
    not _LIVE_API_KEY,
    reason=(
        "TRADING_AI_LIVE_MARKET_DATA_API_KEY is not set - skipping live "
        "market-data provider smoke test (opt-in only)."
    ),
)
def test_live_market_data_quote_smoke() -> None:
    assert _LIVE_API_KEY is not None
    gateway = TwelveDataGateway(api_key=_LIVE_API_KEY)

    quote = asyncio.run(gateway.get_quote("AAPL"))

    assert quote.ticker == "AAPL"
    assert quote.price > 0
    assert quote.source == "twelvedata"
    assert quote.as_of.tzinfo is not None


@pytest.mark.live_provider
@pytest.mark.skipif(
    not _LIVE_API_KEY,
    reason=(
        "TRADING_AI_LIVE_MARKET_DATA_API_KEY is not set - skipping live "
        "market-data provider smoke test (opt-in only)."
    ),
)
def test_live_market_data_price_history_smoke() -> None:
    """One real call, default period only (task scope §12: "не запускать
    десятки live calls") — not all three periods."""
    assert _LIVE_API_KEY is not None
    gateway = TwelveDataGateway(api_key=_LIVE_API_KEY)

    history = asyncio.run(gateway.get_price_history("AAPL", InstrumentHistoryPeriod.ONE_DAY))

    assert history.ticker == "AAPL"
    assert history.source == "twelvedata"
    assert len(history.points) > 1
    assert history.points[-1].close > 0
    assert all(point.timestamp.tzinfo is not None for point in history.points)
    timestamps = [point.timestamp for point in history.points]
    assert timestamps == sorted(timestamps)


@pytest.mark.live_provider
@pytest.mark.skipif(
    not _LIVE_NEWS_API_KEY,
    reason=(
        "TRADING_AI_LIVE_NEWS_API_KEY is not set - skipping live news "
        "provider smoke test (opt-in only)."
    ),
)
def test_live_instrument_news_smoke() -> None:
    """One real call (task scope §12: "не тратить десятки API calls")."""
    assert _LIVE_NEWS_API_KEY is not None
    gateway = FinnhubNewsGateway(api_key=_LIVE_NEWS_API_KEY)

    news = asyncio.run(gateway.get_instrument_news("AAPL"))

    assert news.ticker == "AAPL"
    assert news.source == "finnhub"
    assert len(news.items) >= 0
    if news.items:
        for item in news.items:
            assert item.headline != ""
            assert item.source != ""
            assert item.published_at.tzinfo is not None
            assert item.url.startswith("http://") or item.url.startswith("https://")
        published_ats = [item.published_at for item in news.items]
        assert published_ats == sorted(published_ats, reverse=True)


@pytest.mark.live_provider
@pytest.mark.skipif(
    not _LIVE_LLM_API_KEY,
    reason=(
        "TRADING_AI_LIVE_LLM_API_KEY is not set - skipping live AI "
        "analysis provider smoke test (opt-in only)."
    ),
)
def test_live_instrument_analysis_smoke() -> None:
    """One real call (task scope §19: "не тратить десятки API calls").

    Builds a minimal, hand-constructed `InstrumentAnalysisInput`
    directly — this test exists specifically to confirm the real xAI
    request/response contract (structured output, field names), not to
    re-exercise the use-case's own data-assembly logic (already covered
    by `test_ai_use_cases.py` with fakes).
    """
    assert _LIVE_LLM_API_KEY is not None
    gateway = XAIGateway(api_key=_LIVE_LLM_API_KEY)

    analysis_input = InstrumentAnalysisInput(
        ticker="AAPL",
        price=PriceContextFact(
            ticker="AAPL",
            price=Decimal("213.45"),
            change=Decimal("-2.31"),
            change_percent=Decimal("-1.09"),
            open=Decimal("215.00"),
            high=Decimal("216.00"),
            low=Decimal("212.00"),
            previous_close=Decimal("215.76"),
            volume=48_213_456,
            as_of=datetime.now(timezone.utc),
            quote_available=True,
        ),
        history=HistorySummaryFact(
            period="1M",
            first_close=Decimal("200.00"),
            last_close=Decimal("213.45"),
            min_close=Decimal("195.00"),
            max_close=Decimal("220.00"),
            points_count=22,
            history_available=True,
        ),
        news=(),
        news_available=False,
        horizon=AnalysisHorizon.SHORT,
        horizon_sufficiency=HorizonDataSufficiency.SUFFICIENT,
        horizon_sufficiency_reason="",
    )

    analysis = asyncio.run(gateway.generate_instrument_analysis(analysis_input))

    assert analysis.ticker == "AAPL"
    assert analysis.summary != ""
    assert analysis.price_context != ""
    assert analysis.news_context != ""
    assert len(analysis.risks) >= 1
    assert analysis.disclaimer != ""
    assert analysis.generated_at.tzinfo is not None
    assert analysis.provider == "xai"
    # Phase 2B (Forecast Contract):
    assert analysis.horizon == AnalysisHorizon.SHORT
    assert analysis.forecast_state is not None
    assert analysis.check_after is not None
    assert analysis.check_after > analysis.generated_at
    # No chain-of-thought/internal-reasoning field exists on this type
    # at all (task scope §14) — nothing to strip, nothing to assert
    # away here beyond the structural guarantee of the dataclass itself.


@pytest.mark.live_provider
@pytest.mark.skipif(
    not _LIVE_API_KEY,
    reason=(
        "TRADING_AI_LIVE_MARKET_DATA_API_KEY is not set - skipping live "
        "market-data provider smoke test (opt-in only)."
    ),
)
def test_live_search_instruments_smoke() -> None:
    """Two real calls — Apple and Microsoft (R2 task scope: "Verify
    Apple and Microsoft with real provider calls"), still bounded
    ("не делать много live calls").

    Also verifies the R2 US-common-stock filter against real provider
    data: Twelve Data's raw `/symbol_search` response for "Apple"
    includes non-US listings sharing the AAPL ticker (Colombia, Mexico)
    and a non-equity South African ETN, all excluded — confirmed live
    before this test was written. At `outputsize=120` a few unrelated
    but genuinely US-common-stock companies also match the "Apple"
    substring (e.g. "Apple iSport Group Inc.", ticker AAPI) — expected
    and correct: the filter's job is US-common-stock-only, not
    single-result exact identification, so this asserts AAPL is
    present and ranked first (provider relevance), not `len() == 1`.
    """
    assert _LIVE_API_KEY is not None
    gateway = TwelveDataGateway(api_key=_LIVE_API_KEY)

    apple_results = asyncio.run(gateway.search_instruments("Apple"))
    assert len(apple_results) >= 1
    assert apple_results[0].ticker == "AAPL"
    assert apple_results[0].exchange == "NASDAQ"
    assert apple_results[0].currency == "USD"

    microsoft_results = asyncio.run(gateway.search_instruments("Microsoft"))
    assert len(microsoft_results) >= 1
    assert microsoft_results[0].ticker == "MSFT"
    assert microsoft_results[0].exchange == "NASDAQ"
    assert microsoft_results[0].currency == "USD"

    for result in (*apple_results, *microsoft_results):
        assert result.ticker != ""
        assert result.name != ""
