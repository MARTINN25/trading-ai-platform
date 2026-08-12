"""`GetNewsIntelligence` behavior tests (Phase 2A, task scope §17):
curation/noise exclusion, ranking, bounded count, empty relevant
result, LLM-unavailable degradation, per-item invalid output
degradation, provider-failure propagation, and cache reuse (an item
already persisted is never re-sent to the LLM)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from trading_ai.ai.types import (
    AINewsProviderUnavailableError,
    NewsCandidateFact,
    NewsEnrichmentResult,
    NewsRelationship,
    NewsRelevance,
)
from trading_ai.market_data.types import (
    InstrumentNews,
    InstrumentNewsItem,
    InstrumentSearchResult,
    MarketDataUnavailableError,
)
from trading_ai.news_intelligence.domain import NewNewsIntelligenceRow, PersistedNewsIntelligenceItem
from trading_ai.news_intelligence.use_cases import GetNewsIntelligence

_T = datetime(2026, 8, 10, 15, 0, 0, tzinfo=timezone.utc)


def _raw_item(item_id: str, headline: str, *, minutes_ago: int = 0, summary: str | None = None) -> InstrumentNewsItem:
    return InstrumentNewsItem(
        id=item_id,
        ticker="AAPL",
        headline=headline,
        source="Reuters",
        published_at=_T - timedelta(minutes=minutes_ago),
        url=f"https://example.com/{item_id}",
        summary=summary,
    )


class _FakeNewsUseCase:
    def __init__(self, result: InstrumentNews | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    async def execute(self, raw_ticker: str) -> InstrumentNews:
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


class _FakeRepository:
    def __init__(self, existing: dict[str, PersistedNewsIntelligenceItem] | None = None) -> None:
        self._store: dict[tuple[str, str, str], PersistedNewsIntelligenceItem] = {}
        self._next_id = 1
        if existing:
            for provider_news_id, item in existing.items():
                self._store[("AAPL", "finnhub", provider_news_id)] = item
        self.add_calls: list[NewNewsIntelligenceRow] = []
        self.lookup_calls: list[list[str]] = []

    async def get_existing_for_ticker(
        self, ticker: str, news_provider: str, provider_news_ids: list[str]
    ) -> dict[str, PersistedNewsIntelligenceItem]:
        self.lookup_calls.append(list(provider_news_ids))
        return {
            pid: self._store[(ticker, news_provider, pid)]
            for pid in provider_news_ids
            if (ticker, news_provider, pid) in self._store
        }

    async def add(self, row: NewNewsIntelligenceRow) -> PersistedNewsIntelligenceItem:
        self.add_calls.append(row)
        persisted = PersistedNewsIntelligenceItem(
            id=self._next_id,
            ticker=row.ticker,
            news_provider=row.news_provider,
            provider_news_id=row.provider_news_id,
            headline_original=row.headline_original,
            source=row.source,
            published_at=row.published_at,
            url=row.url,
            enriched=row.enriched,
            summary_ru=row.summary_ru,
            why_it_matters=row.why_it_matters,
            relevance=row.relevance,
            relationship=row.relationship,
            impact_hypothesis=row.impact_hypothesis,
            llm_provider=row.llm_provider,
            llm_model=row.llm_model,
            llm_prompt_version=row.llm_prompt_version,
            llm_schema_version=row.llm_schema_version,
            created_at=_T,
        )
        self._next_id += 1
        self._store[(row.ticker, row.news_provider, row.provider_news_id)] = persisted
        return persisted


def _persisted(
    provider_news_id: str,
    *,
    relationship: NewsRelationship = NewsRelationship.COMPANY,
    relevance: NewsRelevance = NewsRelevance.HIGH,
) -> PersistedNewsIntelligenceItem:
    return PersistedNewsIntelligenceItem(
        id=1,
        ticker="AAPL",
        news_provider="finnhub",
        provider_news_id=provider_news_id,
        headline_original="Cached headline",
        source="Reuters",
        published_at=_T,
        url="https://example.com/cached",
        enriched=True,
        summary_ru="Кэшированное резюме.",
        why_it_matters="Почему важно.",
        relevance=relevance,
        relationship=relationship,
        impact_hypothesis="Возможное влияние.",
        llm_provider="xai",
        llm_model="grok-4.5",
        llm_prompt_version="news-intelligence-v1",
        llm_schema_version="news-intelligence-v1",
        created_at=_T,
    )


class _FakeAIGateway:
    def __init__(
        self,
        results_by_id: dict[str, NewsEnrichmentResult] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._results_by_id = results_by_id or {}
        self._error = error
        self.received_candidates: tuple[NewsCandidateFact, ...] | None = None
        self.call_count = 0
        self.model = "grok-4.5"

    async def generate_news_intelligence(
        self, ticker: str, candidates: tuple[NewsCandidateFact, ...]
    ) -> list[NewsEnrichmentResult]:
        self.call_count += 1
        self.received_candidates = candidates
        if self._error is not None:
            raise self._error
        return [
            self._results_by_id[candidate.id]
            for candidate in candidates
            if candidate.id in self._results_by_id
        ]


def _enrichment(item_id: str, *, relationship: NewsRelationship, relevance: NewsRelevance = NewsRelevance.HIGH) -> NewsEnrichmentResult:
    return NewsEnrichmentResult(
        id=item_id,
        relevance=relevance,
        relationship=relationship,
        summary_ru="Краткое резюме.",
        why_it_matters="Почему это важно.",
        impact_hypothesis="Возможное влияние.",
    )


@pytest.mark.anyio
async def test_noise_items_are_excluded_from_curated_result() -> None:
    raw = [_raw_item("1", "Company earnings beat"), _raw_item("2", "Unrelated wire filler")]
    news = InstrumentNews(ticker="AAPL", source="finnhub", items=tuple(raw))
    gateway = _FakeAIGateway(
        results_by_id={
            "1": _enrichment("1", relationship=NewsRelationship.COMPANY),
            "2": _enrichment("2", relationship=NewsRelationship.NOISE, relevance=NewsRelevance.LOW),
        }
    )
    use_case = GetNewsIntelligence(_FakeNewsUseCase(result=news), _FakeRepository(), gateway)

    result = await use_case.execute("AAPL")

    assert [item.id for item in result.items] == ["1"]


@pytest.mark.anyio
async def test_curated_result_ranked_company_before_sector_before_macro() -> None:
    raw = [_raw_item("1", "Macro headline"), _raw_item("2", "Sector headline"), _raw_item("3", "Company headline")]
    news = InstrumentNews(ticker="AAPL", source="finnhub", items=tuple(raw))
    gateway = _FakeAIGateway(
        results_by_id={
            "1": _enrichment("1", relationship=NewsRelationship.MACRO),
            "2": _enrichment("2", relationship=NewsRelationship.SECTOR),
            "3": _enrichment("3", relationship=NewsRelationship.COMPANY),
        }
    )
    use_case = GetNewsIntelligence(_FakeNewsUseCase(result=news), _FakeRepository(), gateway)

    result = await use_case.execute("AAPL")

    assert [item.id for item in result.items] == ["3", "2", "1"]


@pytest.mark.anyio
async def test_bounded_result_count_caps_curated_items() -> None:
    raw = [_raw_item(str(i), f"Company headline {i}", minutes_ago=i) for i in range(10)]
    news = InstrumentNews(ticker="AAPL", source="finnhub", items=tuple(raw))
    gateway = _FakeAIGateway(
        results_by_id={
            str(i): _enrichment(str(i), relationship=NewsRelationship.COMPANY) for i in range(10)
        }
    )
    use_case = GetNewsIntelligence(_FakeNewsUseCase(result=news), _FakeRepository(), gateway)

    result = await use_case.execute("AAPL")

    assert len(result.items) == 8  # _MAX_CURATED_RESULT


@pytest.mark.anyio
async def test_only_genuinely_relevant_items_returned_not_padded() -> None:
    raw = [_raw_item("1", "Company headline"), _raw_item("2", "Noise headline")]
    news = InstrumentNews(ticker="AAPL", source="finnhub", items=tuple(raw))
    gateway = _FakeAIGateway(
        results_by_id={
            "1": _enrichment("1", relationship=NewsRelationship.COMPANY),
            "2": _enrichment("2", relationship=NewsRelationship.NOISE),
        }
    )
    use_case = GetNewsIntelligence(_FakeNewsUseCase(result=news), _FakeRepository(), gateway)

    result = await use_case.execute("AAPL")

    assert len(result.items) == 1


@pytest.mark.anyio
async def test_empty_raw_news_returns_empty_curated_result() -> None:
    news = InstrumentNews(ticker="AAPL", source="finnhub", items=())
    use_case = GetNewsIntelligence(_FakeNewsUseCase(result=news), _FakeRepository(), ai_gateway=None)

    result = await use_case.execute("AAPL")

    assert result.items == ()


@pytest.mark.anyio
async def test_llm_gateway_unavailable_degrades_to_unenriched_items() -> None:
    raw = [_raw_item("1", "Company headline")]
    news = InstrumentNews(ticker="AAPL", source="finnhub", items=tuple(raw))
    use_case = GetNewsIntelligence(_FakeNewsUseCase(result=news), _FakeRepository(), ai_gateway=None)

    result = await use_case.execute("AAPL")

    assert len(result.items) == 1
    assert result.items[0].enriched is False
    assert result.items[0].summary_ru is None
    assert result.items[0].headline == "Company headline"


@pytest.mark.anyio
async def test_whole_batch_llm_failure_degrades_all_items_without_raising() -> None:
    raw = [_raw_item("1", "Company headline")]
    news = InstrumentNews(ticker="AAPL", source="finnhub", items=tuple(raw))
    gateway = _FakeAIGateway(error=AINewsProviderUnavailableError("down"))
    repository = _FakeRepository()
    use_case = GetNewsIntelligence(_FakeNewsUseCase(result=news), repository, gateway)

    result = await use_case.execute("AAPL")

    assert len(result.items) == 1
    assert result.items[0].enriched is False
    # A failed batch is never persisted as "tried and failed" — it must
    # be retried on a future request, not permanently cached as raw.
    assert repository.add_calls == []


@pytest.mark.anyio
async def test_single_item_missing_from_model_response_degrades_only_that_item() -> None:
    raw = [_raw_item("1", "Company headline"), _raw_item("2", "Other headline")]
    news = InstrumentNews(ticker="AAPL", source="finnhub", items=tuple(raw))
    # The gateway only returns a result for "1" — "2" is silently
    # missing, as if the model omitted or failed to validate it.
    gateway = _FakeAIGateway(results_by_id={"1": _enrichment("1", relationship=NewsRelationship.COMPANY)})
    use_case = GetNewsIntelligence(_FakeNewsUseCase(result=news), _FakeRepository(), gateway)

    result = await use_case.execute("AAPL")

    by_id = {item.id: item for item in result.items}
    assert by_id["1"].enriched is True
    assert by_id["2"].enriched is False


@pytest.mark.anyio
async def test_already_persisted_item_is_not_resent_to_llm() -> None:
    """Cache-reuse (task scope §10): an item already in the repository
    for this ticker must not trigger another LLM call for it."""
    raw = [_raw_item("1", "Company headline")]
    news = InstrumentNews(ticker="AAPL", source="finnhub", items=tuple(raw))
    repository = _FakeRepository(existing={"1": _persisted("1")})
    gateway = _FakeAIGateway()
    use_case = GetNewsIntelligence(_FakeNewsUseCase(result=news), repository, gateway)

    result = await use_case.execute("AAPL")

    assert gateway.call_count == 0
    assert len(result.items) == 1
    assert result.items[0].enriched is True
    assert result.items[0].summary_ru == "Кэшированное резюме."


@pytest.mark.anyio
async def test_mixed_cached_and_new_items_only_sends_new_ones_to_llm() -> None:
    raw = [_raw_item("1", "Cached headline"), _raw_item("2", "New headline")]
    news = InstrumentNews(ticker="AAPL", source="finnhub", items=tuple(raw))
    repository = _FakeRepository(existing={"1": _persisted("1")})
    gateway = _FakeAIGateway(results_by_id={"2": _enrichment("2", relationship=NewsRelationship.COMPANY)})
    use_case = GetNewsIntelligence(_FakeNewsUseCase(result=news), repository, gateway)

    result = await use_case.execute("AAPL")

    assert gateway.call_count == 1
    assert gateway.received_candidates is not None
    assert [candidate.id for candidate in gateway.received_candidates] == ["2"]
    assert len(result.items) == 2


@pytest.mark.anyio
async def test_provider_failure_propagates_unchanged() -> None:
    """Finnhub failure is a hard failure — never masked by the
    enrichment layer (task scope §16)."""
    use_case = GetNewsIntelligence(
        _FakeNewsUseCase(error=MarketDataUnavailableError("boom")),
        _FakeRepository(),
        ai_gateway=None,
    )

    with pytest.raises(MarketDataUnavailableError):
        await use_case.execute("AAPL")


@pytest.mark.anyio
async def test_successful_enrichment_is_persisted() -> None:
    raw = [_raw_item("1", "Company headline")]
    news = InstrumentNews(ticker="AAPL", source="finnhub", items=tuple(raw))
    repository = _FakeRepository()
    gateway = _FakeAIGateway(results_by_id={"1": _enrichment("1", relationship=NewsRelationship.COMPANY)})
    use_case = GetNewsIntelligence(_FakeNewsUseCase(result=news), repository, gateway)

    await use_case.execute("AAPL")

    assert len(repository.add_calls) == 1
    assert repository.add_calls[0].enriched is True
    assert repository.add_calls[0].relationship == NewsRelationship.COMPANY


@pytest.mark.anyio
async def test_company_name_resolver_failure_does_not_break_execution() -> None:
    class _FailingSearch:
        async def execute(self, raw_query: str) -> list[InstrumentSearchResult]:
            raise RuntimeError("search boom")

    raw = [_raw_item("1", "Company headline")]
    news = InstrumentNews(ticker="AAPL", source="finnhub", items=tuple(raw))
    gateway = _FakeAIGateway(results_by_id={"1": _enrichment("1", relationship=NewsRelationship.COMPANY)})
    use_case = GetNewsIntelligence(
        _FakeNewsUseCase(result=news), _FakeRepository(), gateway, search_use_case=_FailingSearch()
    )

    result = await use_case.execute("AAPL")

    assert len(result.items) == 1
