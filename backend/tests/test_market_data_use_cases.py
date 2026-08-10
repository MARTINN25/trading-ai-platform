"""Use-case tests for `market_data.use_cases` — fake gateway only, no httpx/DB."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from trading_ai.market_data.types import (
    InstrumentHistoryPeriod,
    InstrumentNews,
    InstrumentNewsItem,
    InstrumentSnapshot,
    InvalidPeriodError,
    MarketDataUnavailableError,
    PriceHistory,
    PricePoint,
)
from trading_ai.market_data.use_cases import (
    GetInstrumentDetails,
    GetInstrumentNews,
    GetInstrumentPriceHistory,
)
from trading_ai.watchlist.domain import InvalidTickerError


class FakeInstrumentGateway:
    """In-memory test double — mirrors `TwelveDataGateway`'s/`FinnhubNewsGateway`'s
    methods, no httpx."""

    def __init__(
        self,
        snapshot: InstrumentSnapshot | None = None,
        history: PriceHistory | None = None,
        news: InstrumentNews | None = None,
    ) -> None:
        self._snapshot = snapshot
        self._history = history
        self._news = news
        self.received_ticker: str | None = None
        self.received_period: InstrumentHistoryPeriod | None = None

    async def get_instrument_snapshot(self, ticker: str) -> InstrumentSnapshot:
        self.received_ticker = ticker
        assert self._snapshot is not None
        return self._snapshot

    async def get_price_history(
        self, ticker: str, period: InstrumentHistoryPeriod
    ) -> PriceHistory:
        self.received_ticker = ticker
        self.received_period = period
        assert self._history is not None
        return self._history

    async def get_instrument_news(self, ticker: str) -> InstrumentNews:
        self.received_ticker = ticker
        assert self._news is not None
        return self._news


def _snapshot(ticker: str = "AAPL") -> InstrumentSnapshot:
    return InstrumentSnapshot(
        ticker=ticker,
        price=Decimal("213.45"),
        change=Decimal("2.31"),
        change_percent=Decimal("1.09"),
        open=Decimal("210.00"),
        high=Decimal("214.20"),
        low=Decimal("209.50"),
        previous_close=Decimal("211.14"),
        volume=48_213_456,
        as_of=datetime.now(timezone.utc),
        source="twelvedata",
    )


def _history(
    ticker: str = "AAPL", period: InstrumentHistoryPeriod = InstrumentHistoryPeriod.ONE_DAY
) -> PriceHistory:
    return PriceHistory(
        ticker=ticker,
        period=period,
        source="twelvedata",
        points=(
            PricePoint(
                timestamp=datetime.now(timezone.utc),
                open=Decimal("306.65"),
                high=Decimal("306.73"),
                low=Decimal("306.56"),
                close=Decimal("306.62"),
                volume=31152,
            ),
        ),
    )


def _news(ticker: str = "AAPL", items: tuple[InstrumentNewsItem, ...] | None = None) -> InstrumentNews:
    if items is None:
        items = (
            InstrumentNewsItem(
                id="1",
                ticker=ticker,
                headline="Apple stock rises",
                source="Reuters",
                published_at=datetime.now(timezone.utc),
                url="https://example.com/article",
                summary="Apple stock rose today.",
            ),
        )
    return InstrumentNews(ticker=ticker, source="finnhub", items=items)


@pytest.mark.anyio
async def test_get_instrument_details_normalizes_ticker_before_calling_gateway() -> None:
    gateway = FakeInstrumentGateway(snapshot=_snapshot())
    use_case = GetInstrumentDetails(gateway)

    snapshot = await use_case.execute("  aapl  ")

    assert gateway.received_ticker == "AAPL"
    assert snapshot.ticker == "AAPL"


@pytest.mark.anyio
async def test_get_instrument_details_invalid_ticker_raises_before_gateway_call() -> None:
    gateway = FakeInstrumentGateway()
    use_case = GetInstrumentDetails(gateway)

    with pytest.raises(InvalidTickerError):
        await use_case.execute("")

    assert gateway.received_ticker is None


@pytest.mark.anyio
async def test_get_instrument_price_history_normalizes_ticker_and_maps_period() -> None:
    gateway = FakeInstrumentGateway(history=_history(period=InstrumentHistoryPeriod.FIVE_DAY))
    use_case = GetInstrumentPriceHistory(gateway)

    history = await use_case.execute("  aapl  ", "5D")

    assert gateway.received_ticker == "AAPL"
    assert gateway.received_period == InstrumentHistoryPeriod.FIVE_DAY
    assert history.period == InstrumentHistoryPeriod.FIVE_DAY
    assert len(history.points) == 1


@pytest.mark.parametrize("period_value", ["1D", "5D", "1M"])
@pytest.mark.anyio
async def test_get_instrument_price_history_accepts_each_supported_period(
    period_value: str,
) -> None:
    gateway = FakeInstrumentGateway(history=_history(period=InstrumentHistoryPeriod(period_value)))
    use_case = GetInstrumentPriceHistory(gateway)

    history = await use_case.execute("AAPL", period_value)

    assert gateway.received_period == InstrumentHistoryPeriod(period_value)
    assert history.period.value == period_value


@pytest.mark.anyio
async def test_get_instrument_price_history_invalid_period_raises_before_gateway_call() -> None:
    gateway = FakeInstrumentGateway()
    use_case = GetInstrumentPriceHistory(gateway)

    with pytest.raises(InvalidPeriodError):
        await use_case.execute("AAPL", "2Y")

    assert gateway.received_ticker is None
    assert gateway.received_period is None


@pytest.mark.anyio
async def test_get_instrument_price_history_invalid_ticker_raises_before_gateway_call() -> None:
    gateway = FakeInstrumentGateway()
    use_case = GetInstrumentPriceHistory(gateway)

    with pytest.raises(InvalidTickerError):
        await use_case.execute("", "1D")

    assert gateway.received_ticker is None


@pytest.mark.anyio
async def test_get_instrument_price_history_successful_return() -> None:
    gateway = FakeInstrumentGateway(history=_history())
    use_case = GetInstrumentPriceHistory(gateway)

    history = await use_case.execute("AAPL", "1D")

    assert history.ticker == "AAPL"
    assert history.source == "twelvedata"
    assert history.points[0].close == Decimal("306.62")


@pytest.mark.anyio
async def test_get_instrument_news_normalizes_ticker_before_calling_gateway() -> None:
    gateway = FakeInstrumentGateway(news=_news())
    use_case = GetInstrumentNews(gateway)

    news = await use_case.execute("  aapl  ")

    assert gateway.received_ticker == "AAPL"
    assert news.ticker == "AAPL"


@pytest.mark.anyio
async def test_get_instrument_news_invalid_ticker_raises_before_gateway_call() -> None:
    gateway = FakeInstrumentGateway()
    use_case = GetInstrumentNews(gateway)

    with pytest.raises(InvalidTickerError):
        await use_case.execute("")

    assert gateway.received_ticker is None


@pytest.mark.anyio
async def test_get_instrument_news_successful_return() -> None:
    gateway = FakeInstrumentGateway(news=_news())
    use_case = GetInstrumentNews(gateway)

    news = await use_case.execute("AAPL")

    assert news.source == "finnhub"
    assert len(news.items) == 1
    assert news.items[0].headline == "Apple stock rises"


@pytest.mark.anyio
async def test_get_instrument_news_empty_list_is_returned_as_is() -> None:
    gateway = FakeInstrumentGateway(news=_news(items=()))
    use_case = GetInstrumentNews(gateway)

    news = await use_case.execute("AAPL")

    assert news.items == ()


@pytest.mark.anyio
async def test_get_instrument_news_provider_error_propagates() -> None:
    class _FailingGateway:
        async def get_instrument_news(self, ticker: str) -> InstrumentNews:
            raise MarketDataUnavailableError("boom")

    use_case = GetInstrumentNews(_FailingGateway())

    with pytest.raises(MarketDataUnavailableError):
        await use_case.execute("AAPL")
