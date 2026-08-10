"""Use-case tests for `ai.use_cases.GenerateInstrumentAnalysis` — fake
use cases/gateway only, no httpx/DB."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from trading_ai.ai.types import (
    AIInsufficientDataError,
    InstrumentAnalysis,
    InstrumentAnalysisInput,
)
from trading_ai.ai.use_cases import GenerateInstrumentAnalysis
from trading_ai.market_data.types import (
    InstrumentHistoryPeriod,
    InstrumentNews,
    InstrumentNewsItem,
    InstrumentSnapshot,
    MarketDataUnavailableError,
    PriceHistory,
    PricePoint,
)
from trading_ai.watchlist.domain import InvalidTickerError


def _snapshot(ticker: str = "AAPL") -> InstrumentSnapshot:
    return InstrumentSnapshot(
        ticker=ticker,
        price=Decimal("213.45"),
        change=Decimal("-2.31"),
        change_percent=Decimal("-1.09"),
        open=Decimal("215.00"),
        high=Decimal("216.00"),
        low=Decimal("212.00"),
        previous_close=Decimal("215.76"),
        volume=48_213_456,
        as_of=datetime.now(timezone.utc),
        source="twelvedata",
    )


def _history(ticker: str = "AAPL") -> PriceHistory:
    return PriceHistory(
        ticker=ticker,
        period=InstrumentHistoryPeriod.ONE_MONTH,
        source="twelvedata",
        points=(
            PricePoint(
                timestamp=datetime.now(timezone.utc),
                open=Decimal("200.00"),
                high=Decimal("205.00"),
                low=Decimal("198.00"),
                close=Decimal("200.00"),
                volume=1000,
            ),
            PricePoint(
                timestamp=datetime.now(timezone.utc),
                open=Decimal("213.00"),
                high=Decimal("214.00"),
                low=Decimal("212.00"),
                close=Decimal("213.45"),
                volume=2000,
            ),
        ),
    )


def _news(ticker: str = "AAPL", count: int = 1) -> InstrumentNews:
    items = tuple(
        InstrumentNewsItem(
            id=str(i),
            ticker=ticker,
            headline=f"Headline {i}",
            source="Reuters",
            published_at=datetime.now(timezone.utc),
            url="https://example.com/a",
            summary=f"Summary {i}",
        )
        for i in range(count)
    )
    return InstrumentNews(ticker=ticker, source="finnhub", items=items)


class FakeDetailsUseCase:
    def __init__(self, result: InstrumentSnapshot | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.received_ticker: str | None = None

    async def execute(self, raw_ticker: str) -> InstrumentSnapshot:
        self.received_ticker = raw_ticker
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


class FakeHistoryUseCase:
    def __init__(self, result: PriceHistory | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.received_args: tuple[str, str] | None = None

    async def execute(self, raw_ticker: str, raw_period: str) -> PriceHistory:
        self.received_args = (raw_ticker, raw_period)
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


class FakeNewsUseCase:
    def __init__(self, result: InstrumentNews | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.received_ticker: str | None = None

    async def execute(self, raw_ticker: str) -> InstrumentNews:
        self.received_ticker = raw_ticker
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


class FakeAIGateway:
    def __init__(self, result: InstrumentAnalysis | None = None) -> None:
        self._result = result
        self.received_input: InstrumentAnalysisInput | None = None

    async def generate_instrument_analysis(
        self, analysis_input: InstrumentAnalysisInput
    ) -> InstrumentAnalysis:
        self.received_input = analysis_input
        if self._result is not None:
            return self._result
        return InstrumentAnalysis(
            ticker=analysis_input.ticker,
            generated_at=datetime.now(timezone.utc),
            summary="s",
            price_context="p",
            news_context="n",
            risks=("r",),
            disclaimer="d",
            provider="xai",
            model="grok-4.5",
        )


def _use_case(
    details: FakeDetailsUseCase,
    history: FakeHistoryUseCase,
    news: FakeNewsUseCase | None,
    ai_gateway: FakeAIGateway | None = None,
) -> tuple[GenerateInstrumentAnalysis, FakeAIGateway]:
    gateway = ai_gateway or FakeAIGateway()
    use_case = GenerateInstrumentAnalysis(
        details_use_case=details,
        history_use_case=history,
        news_use_case=news,
        ai_gateway=gateway,
    )
    return use_case, gateway


@pytest.mark.anyio
async def test_generate_instrument_analysis_success() -> None:
    details = FakeDetailsUseCase(result=_snapshot())
    history = FakeHistoryUseCase(result=_history())
    news = FakeNewsUseCase(result=_news())
    use_case, gateway = _use_case(details, history, news)

    analysis = await use_case.execute("AAPL")

    assert analysis.ticker == "AAPL"
    assert gateway.received_input is not None
    assert gateway.received_input.price.quote_available is True
    assert gateway.received_input.history.history_available is True
    assert gateway.received_input.news_available is True
    assert len(gateway.received_input.news) == 1


@pytest.mark.anyio
async def test_generate_instrument_analysis_normalizes_ticker() -> None:
    details = FakeDetailsUseCase(result=_snapshot())
    history = FakeHistoryUseCase(result=_history())
    news = FakeNewsUseCase(result=_news())
    use_case, gateway = _use_case(details, history, news)

    await use_case.execute("  aapl  ")

    assert details.received_ticker == "AAPL"
    assert history.received_args == ("AAPL", "1M")
    assert news.received_ticker == "AAPL"
    assert gateway.received_input is not None
    assert gateway.received_input.ticker == "AAPL"


@pytest.mark.anyio
async def test_generate_instrument_analysis_invalid_ticker_raises_before_any_call() -> None:
    details = FakeDetailsUseCase(result=_snapshot())
    history = FakeHistoryUseCase(result=_history())
    news = FakeNewsUseCase(result=_news())
    use_case, gateway = _use_case(details, history, news)

    with pytest.raises(InvalidTickerError):
        await use_case.execute("")

    assert details.received_ticker is None
    assert gateway.received_input is None


@pytest.mark.anyio
async def test_generate_instrument_analysis_degraded_when_news_unavailable() -> None:
    details = FakeDetailsUseCase(result=_snapshot())
    history = FakeHistoryUseCase(result=_history())
    news = FakeNewsUseCase(error=MarketDataUnavailableError("boom"))
    use_case, gateway = _use_case(details, history, news)

    analysis = await use_case.execute("AAPL")

    assert analysis.ticker == "AAPL"
    assert gateway.received_input is not None
    assert gateway.received_input.news_available is False
    assert gateway.received_input.news == ()
    # Quote still made it through — this is a degraded, not a failed, analysis.
    assert gateway.received_input.price.quote_available is True


@pytest.mark.anyio
async def test_generate_instrument_analysis_degraded_when_news_not_configured() -> None:
    """`news_use_case=None` (provider not configured at all) must degrade
    exactly like a failed news call, not raise."""
    details = FakeDetailsUseCase(result=_snapshot())
    history = FakeHistoryUseCase(result=_history())
    use_case, gateway = _use_case(details, history, news=None)

    analysis = await use_case.execute("AAPL")

    assert analysis.ticker == "AAPL"
    assert gateway.received_input is not None
    assert gateway.received_input.news_available is False


@pytest.mark.anyio
async def test_generate_instrument_analysis_degraded_when_history_unavailable() -> None:
    details = FakeDetailsUseCase(result=_snapshot())
    history = FakeHistoryUseCase(error=MarketDataUnavailableError("boom"))
    news = FakeNewsUseCase(result=_news())
    use_case, gateway = _use_case(details, history, news)

    analysis = await use_case.execute("AAPL")

    assert analysis.ticker == "AAPL"
    assert gateway.received_input is not None
    assert gateway.received_input.history.history_available is False
    assert gateway.received_input.history.points_count == 0
    assert gateway.received_input.price.quote_available is True


@pytest.mark.anyio
async def test_generate_instrument_analysis_insufficient_data_when_quote_unavailable() -> None:
    details = FakeDetailsUseCase(error=MarketDataUnavailableError("boom"))
    history = FakeHistoryUseCase(result=_history())
    news = FakeNewsUseCase(result=_news())
    use_case, gateway = _use_case(details, history, news)

    with pytest.raises(AIInsufficientDataError):
        await use_case.execute("AAPL")

    # The LLM gateway must never be called with zero real facts.
    assert gateway.received_input is None


@pytest.mark.anyio
async def test_generate_instrument_analysis_provider_error_propagates_from_gateway() -> None:
    class _FailingAIGateway:
        async def generate_instrument_analysis(
            self, analysis_input: InstrumentAnalysisInput
        ) -> InstrumentAnalysis:
            raise MarketDataUnavailableError("boom")

    details = FakeDetailsUseCase(result=_snapshot())
    history = FakeHistoryUseCase(result=_history())
    news = FakeNewsUseCase(result=_news())
    use_case = GenerateInstrumentAnalysis(details, history, news, _FailingAIGateway())

    with pytest.raises(MarketDataUnavailableError):
        await use_case.execute("AAPL")


@pytest.mark.anyio
async def test_generate_instrument_analysis_news_bounded_to_five_items() -> None:
    details = FakeDetailsUseCase(result=_snapshot())
    history = FakeHistoryUseCase(result=_history())
    news = FakeNewsUseCase(result=_news(count=10))
    use_case, gateway = _use_case(details, history, news)

    await use_case.execute("AAPL")

    assert gateway.received_input is not None
    assert len(gateway.received_input.news) == 5


@pytest.mark.anyio
async def test_generate_instrument_analysis_news_headline_and_summary_truncated() -> None:
    long_headline = "H" * 500
    long_summary = "S" * 900
    news_with_long_text = InstrumentNews(
        ticker="AAPL",
        source="finnhub",
        items=(
            InstrumentNewsItem(
                id="1",
                ticker="AAPL",
                headline=long_headline,
                source="Reuters",
                published_at=datetime.now(timezone.utc),
                url="https://example.com/a",
                summary=long_summary,
            ),
        ),
    )
    details = FakeDetailsUseCase(result=_snapshot())
    history = FakeHistoryUseCase(result=_history())
    news = FakeNewsUseCase(result=news_with_long_text)
    use_case, gateway = _use_case(details, history, news)

    await use_case.execute("AAPL")

    assert gateway.received_input is not None
    fact = gateway.received_input.news[0]
    assert len(fact.headline) <= 200
    assert fact.summary is not None
    assert len(fact.summary) <= 400
