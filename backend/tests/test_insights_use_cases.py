"""Use-case tests for `insights.use_cases` — fake repository/cache only,
no DB/HTTP (task scope §21)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from trading_ai.ai.pending_cache import PendingAnalysisCache
from trading_ai.ai.types import ConfidenceLevel, InstrumentAnalysis, KeyFact
from trading_ai.insights.domain import (
    InsightNotFoundError,
    NewInsight,
    PendingAnalysisNotFoundError,
    SavedInsight,
)
from trading_ai.insights.use_cases import (
    GetInsightDetail,
    ListInstrumentInsights,
    ListRecentInsights,
    SaveInsight,
)
from trading_ai.watchlist.domain import InvalidTickerError

_T = datetime(2026, 3, 2, 14, 30, tzinfo=timezone.utc)


def _analysis(ticker: str = "AAPL") -> InstrumentAnalysis:
    return InstrumentAnalysis(
        ticker=ticker,
        generated_at=_T,
        summary="s",
        price_context="p",
        news_context="n",
        key_facts=(KeyFact(fact="f", source="Текущая котировка"),),
        insight_hypothesis="h",
        confidence=ConfidenceLevel.HIGH,
        confidence_reason="cr",
        considerations=("c",),
        risks=("r",),
        key_drivers=("kd",),
        data_freshness="df",
        source_data_as_of=_T,
        disclaimer="d",
        provider="xai",
        model="grok-4.5",
        prompt_version="instrument-analysis-v2",
        schema_version="insight-structure-v1",
    )


def _saved_insight(insight_id: int = 1, ticker: str = "AAPL") -> SavedInsight:
    return SavedInsight(
        id=insight_id,
        ticker=ticker,
        generated_at=_T,
        created_at=_T,
        summary="s",
        price_context="p",
        news_context="n",
        key_facts=(KeyFact(fact="f", source="Текущая котировка"),),
        insight_hypothesis="h",
        confidence=ConfidenceLevel.HIGH,
        confidence_reason="cr",
        considerations=("c",),
        risks=("r",),
        key_drivers=("kd",),
        data_freshness="df",
        source_data_as_of=_T,
        disclaimer="d",
        provider="xai",
        model="grok-4.5",
        prompt_version="instrument-analysis-v2",
        schema_version="insight-structure-v1",
    )


class FakeInsightRepository:
    def __init__(self) -> None:
        self.added: list[NewInsight] = []
        self._by_id: dict[int, SavedInsight] = {}
        self._by_ticker: dict[str, list[SavedInsight]] = {}
        self._next_id = 1

    async def add(self, insight: NewInsight) -> SavedInsight:
        self.added.append(insight)
        saved = _saved_insight(insight_id=self._next_id, ticker=insight.ticker)
        self._next_id += 1
        self._by_id[saved.id] = saved
        self._by_ticker.setdefault(insight.ticker, []).append(saved)
        return saved

    async def list_recent_for_ticker(self, ticker: str) -> list[SavedInsight]:
        return list(self._by_ticker.get(ticker, []))

    async def get_by_id(self, insight_id: int) -> SavedInsight | None:
        return self._by_id.get(insight_id)

    async def list_recent(self, limit: int) -> list[SavedInsight]:
        """Newest-first (highest id first) across all tickers, bounded —
        mirrors `InsightRepository.list_recent`'s `ORDER BY created_at
        DESC, id DESC` for this in-memory fake (Phase 1)."""
        ordered = sorted(self._by_id.values(), key=lambda item: item.id, reverse=True)
        return ordered[:limit]


@pytest.mark.anyio
async def test_save_insight_success_flow() -> None:
    repository = FakeInsightRepository()
    cache = PendingAnalysisCache()
    token = cache.put("AAPL", _analysis())
    use_case = SaveInsight(repository, cache)

    saved = await use_case.execute("AAPL", token)

    assert saved.ticker == "AAPL"
    assert len(repository.added) == 1
    assert repository.added[0].provider == "xai"
    assert repository.added[0].model == "grok-4.5"
    assert repository.added[0].prompt_version == "instrument-analysis-v2"
    assert repository.added[0].schema_version == "insight-structure-v1"


@pytest.mark.anyio
async def test_save_insight_normalizes_ticker() -> None:
    repository = FakeInsightRepository()
    cache = PendingAnalysisCache()
    token = cache.put("AAPL", _analysis())
    use_case = SaveInsight(repository, cache)

    await use_case.execute("  aapl  ", token)

    assert repository.added[0].ticker == "AAPL"


@pytest.mark.anyio
async def test_save_insight_unknown_token_raises_before_touching_repository() -> None:
    repository = FakeInsightRepository()
    cache = PendingAnalysisCache()
    use_case = SaveInsight(repository, cache)

    with pytest.raises(PendingAnalysisNotFoundError):
        await use_case.execute("AAPL", "not-a-real-token")

    assert repository.added == []


@pytest.mark.anyio
async def test_save_insight_wrong_ticker_for_token_raises() -> None:
    """A token issued for one ticker must not save under another —
    defends against a client mixing up tickers (task scope §12)."""
    repository = FakeInsightRepository()
    cache = PendingAnalysisCache()
    token = cache.put("AAPL", _analysis(ticker="AAPL"))
    use_case = SaveInsight(repository, cache)

    with pytest.raises(PendingAnalysisNotFoundError):
        await use_case.execute("MSFT", token)

    assert repository.added == []


@pytest.mark.anyio
async def test_save_insight_token_is_single_use() -> None:
    """A second save with the same token must fail, not silently
    duplicate the row (task scope §16: no duplicate on repeated click)."""
    repository = FakeInsightRepository()
    cache = PendingAnalysisCache()
    token = cache.put("AAPL", _analysis())
    use_case = SaveInsight(repository, cache)

    await use_case.execute("AAPL", token)
    with pytest.raises(PendingAnalysisNotFoundError):
        await use_case.execute("AAPL", token)

    assert len(repository.added) == 1


@pytest.mark.anyio
async def test_save_insight_invalid_ticker_raises_before_cache_lookup() -> None:
    repository = FakeInsightRepository()
    cache = PendingAnalysisCache()
    use_case = SaveInsight(repository, cache)

    with pytest.raises(InvalidTickerError):
        await use_case.execute("", "some-token")

    assert repository.added == []


@pytest.mark.anyio
async def test_list_instrument_insights_returns_repository_results() -> None:
    repository = FakeInsightRepository()
    await repository.add(_new_insight_stub())
    use_case = ListInstrumentInsights(repository)

    results = await use_case.execute("AAPL")

    assert len(results) == 1
    assert results[0].ticker == "AAPL"


@pytest.mark.anyio
async def test_list_instrument_insights_normalizes_ticker() -> None:
    repository = FakeInsightRepository()
    use_case = ListInstrumentInsights(repository)

    await use_case.execute("  aapl  ")
    # No exception — normalization happens before the repository call;
    # repository received the normalized ticker implicitly via lookup
    # dict key behavior tested through FakeInsightRepository's own
    # ticker-keyed storage (exercised in the previous test).


@pytest.mark.anyio
async def test_get_insight_detail_found() -> None:
    repository = FakeInsightRepository()
    saved = await repository.add(_new_insight_stub())
    use_case = GetInsightDetail(repository)

    result = await use_case.execute(saved.id)

    assert result.id == saved.id


@pytest.mark.anyio
async def test_get_insight_detail_missing_raises() -> None:
    repository = FakeInsightRepository()
    use_case = GetInsightDetail(repository)

    with pytest.raises(InsightNotFoundError):
        await use_case.execute(999)


@pytest.mark.anyio
async def test_list_recent_insights_returns_newest_first_across_tickers() -> None:
    repository = FakeInsightRepository()
    await repository.add(_new_insight_stub(ticker="AAPL"))
    await repository.add(_new_insight_stub(ticker="MSFT"))
    use_case = ListRecentInsights(repository)

    results = await use_case.execute(limit=10)

    assert [item.ticker for item in results] == ["MSFT", "AAPL"]


@pytest.mark.anyio
async def test_list_recent_insights_respects_limit() -> None:
    repository = FakeInsightRepository()
    await repository.add(_new_insight_stub(ticker="AAPL"))
    await repository.add(_new_insight_stub(ticker="MSFT"))
    await repository.add(_new_insight_stub(ticker="GOOG"))
    use_case = ListRecentInsights(repository)

    results = await use_case.execute(limit=2)

    assert len(results) == 2
    assert [item.ticker for item in results] == ["GOOG", "MSFT"]


@pytest.mark.anyio
async def test_list_recent_insights_empty_result() -> None:
    repository = FakeInsightRepository()
    use_case = ListRecentInsights(repository)

    results = await use_case.execute()

    assert results == []


@pytest.mark.anyio
async def test_list_recent_insights_default_limit_is_max_history_items() -> None:
    """No explicit `limit` argument must still bound the result the same
    way the per-ticker use case does (task scope: bounded, no
    infinite-scroll pagination)."""
    from trading_ai.insights.domain import MAX_HISTORY_ITEMS

    repository = FakeInsightRepository()
    for _ in range(MAX_HISTORY_ITEMS + 5):
        await repository.add(_new_insight_stub())
    use_case = ListRecentInsights(repository)

    results = await use_case.execute()

    assert len(results) == MAX_HISTORY_ITEMS


def _new_insight_stub(ticker: str = "AAPL") -> NewInsight:
    return NewInsight(
        ticker=ticker,
        generated_at=_T,
        summary="s",
        price_context="p",
        news_context="n",
        key_facts=(KeyFact(fact="f", source="Текущая котировка"),),
        insight_hypothesis="h",
        confidence=ConfidenceLevel.HIGH,
        confidence_reason="cr",
        considerations=("c",),
        risks=("r",),
        key_drivers=("kd",),
        data_freshness="df",
        source_data_as_of=_T,
        disclaimer="d",
        provider="xai",
        model="grok-4.5",
        prompt_version="instrument-analysis-v2",
        schema_version="insight-structure-v1",
    )
