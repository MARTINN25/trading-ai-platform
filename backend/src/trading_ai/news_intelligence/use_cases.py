"""News Intelligence application use case (Phase 2A, FR-064, UJ-034).

`GetNewsIntelligence` coordinates: the existing raw-news use case
(`market_data.use_cases.GetInstrumentNews`), deterministic preprocessing
(`preprocessing.py`), the persisted enrichment cache
(`repository.py` — this *is* the "process once, reuse" mechanism, task
scope §10), and the LLM gateway's batch enrichment call
(`ai.gateway.XAIGateway.generate_news_intelligence`). It never talks to
Finnhub/xAI SDKs directly.

Reuse/persistence policy (task scope §10, §16): only *successfully*
enriched items are ever persisted. An item that fails enrichment — the
whole batch call failed, or the model didn't return/validate that
specific item — is never written to the cache as "tried and failed"; it
is shown to the user this one time as an unenriched (raw) item and will
be attempted again on a future request once the LLM is available. A
`NOISE`-classified item *is* a successful result and *is* persisted —
it will not be re-sent to the model on a later request, it is simply
excluded from the curated feed at display time.
"""

from __future__ import annotations

import logging
from typing import Protocol

from trading_ai.ai.news_prompts import NEWS_PROMPT_VERSION
from trading_ai.ai.types import (
    NEWS_SCHEMA_VERSION,
    AINewsEnrichmentError,
    NewsCandidateFact,
    NewsEnrichmentResult,
    NewsRelationship,
    NewsRelevance,
)
from trading_ai.market_data.types import InstrumentNews, InstrumentNewsItem, InstrumentSearchResult
from trading_ai.news_intelligence.domain import (
    CuratedNews,
    CuratedNewsItem,
    NewNewsIntelligenceRow,
    PersistedNewsIntelligenceItem,
)
from trading_ai.news_intelligence.preprocessing import (
    deduplicate_items,
    mentions_company_name,
    mentions_ticker,
)
from trading_ai.watchlist.domain import normalize_ticker

logger = logging.getLogger(__name__)

# Deduped candidates beyond this are dropped *before* even being
# considered for LLM enrichment — bounds both the LLM batch size
# (mirrors `ai.gateway._MAX_NEWS_ITEMS_PER_BATCH`) and the DB lookup
# size. Finnhub's own gateway already caps raw items at 10
# (`news_gateway._DEFAULT_LIMIT`), so this is rarely the limiting
# factor in practice — it exists for correctness if that cap ever
# changes, not as the primary noise-reduction mechanism (that's
# `_MAX_CURATED_RESULT` below, applied after classification).
_MAX_CANDIDATES = 10

# The bounded, curated result size shown to the user (task scope §15:
# "preserve a bounded result count... if only 2 genuinely relevant
# items exist, return 2 rather than padding to 10").
_MAX_CURATED_RESULT = 8

_MAX_HEADLINE_CHARS = 200
_MAX_SUMMARY_CHARS = 400

_RELATIONSHIP_RANK: dict[NewsRelationship | None, int] = {
    NewsRelationship.COMPANY: 0,
    NewsRelationship.SECTOR: 1,
    NewsRelationship.MACRO: 2,
    NewsRelationship.MARKET: 3,
    NewsRelationship.INDIRECT: 4,
    None: 5,
}
_RELEVANCE_RANK: dict[NewsRelevance | None, int] = {
    NewsRelevance.HIGH: 0,
    NewsRelevance.MEDIUM: 1,
    NewsRelevance.LOW: 2,
    None: 1,
}


class _InstrumentNewsUseCaseLike(Protocol):
    async def execute(self, raw_ticker: str) -> InstrumentNews: ...


class _NewsAIGatewayLike(Protocol):
    @property
    def model(self) -> str: ...

    async def generate_news_intelligence(
        self, ticker: str, candidates: tuple[NewsCandidateFact, ...]
    ) -> list[NewsEnrichmentResult]: ...


class _NewsIntelligenceRepositoryLike(Protocol):
    async def get_existing_for_ticker(
        self, ticker: str, news_provider: str, provider_news_ids: list[str]
    ) -> dict[str, PersistedNewsIntelligenceItem]: ...

    async def add(self, row: NewNewsIntelligenceRow) -> PersistedNewsIntelligenceItem: ...


class _SearchInstrumentsLike(Protocol):
    async def execute(self, raw_query: str) -> list[InstrumentSearchResult]: ...


class GetNewsIntelligence:
    def __init__(
        self,
        news_use_case: _InstrumentNewsUseCaseLike,
        repository: _NewsIntelligenceRepositoryLike,
        ai_gateway: _NewsAIGatewayLike | None,
        search_use_case: _SearchInstrumentsLike | None = None,
    ) -> None:
        self._news_use_case = news_use_case
        self._repository = repository
        # `None` when xAI isn't configured — degrades to deterministic-
        # only curation, never a hard failure (task scope §16).
        self._ai_gateway = ai_gateway
        # `None` is fine — only used for the best-effort "company name
        # mention" signal (task scope §5: "where reliable").
        self._search_use_case = search_use_case

    async def execute(self, raw_ticker: str) -> CuratedNews:
        ticker = normalize_ticker(raw_ticker)
        news = await self._news_use_case.execute(ticker)

        deduped = deduplicate_items(news.items)
        if not deduped:
            return CuratedNews(ticker=ticker, source=news.source, items=())

        # The mention-based priority sort (and its company-name lookup)
        # only matters when there are more deduped candidates than fit
        # in one LLM batch — the common case (Finnhub's own cap already
        # matches `_MAX_CANDIDATES`) skips it entirely, which also means
        # a fully-cached refresh never pays for a search call it has no
        # use for (task scope §10: reuse must actually be cheap, not
        # just avoid the LLM call).
        working_set = deduped
        if len(deduped) > _MAX_CANDIDATES:
            company_name = await self._resolve_company_name(ticker, needed=True)
            working_set = sorted(
                deduped,
                key=lambda item: (
                    not mentions_ticker(f"{item.headline} {item.summary or ''}", ticker),
                    not mentions_company_name(f"{item.headline} {item.summary or ''}", company_name),
                    -item.published_at.timestamp(),
                ),
            )[:_MAX_CANDIDATES]

        existing = await self._repository.get_existing_for_ticker(
            ticker, news.source, [item.id for item in working_set]
        )
        to_enrich = [item for item in working_set if item.id not in existing]

        newly_persisted: dict[str, PersistedNewsIntelligenceItem] = {}
        if to_enrich and self._ai_gateway is not None:
            newly_persisted = await self._enrich_and_persist(ticker, news.source, to_enrich)

        curated_items = [
            self._to_curated_item(item, existing.get(item.id) or newly_persisted.get(item.id))
            for item in working_set
        ]
        curated_items = [
            item for item in curated_items if item.relationship != NewsRelationship.NOISE
        ]
        curated_items.sort(
            key=lambda item: (
                _RELATIONSHIP_RANK[item.relationship],
                _RELEVANCE_RANK[item.relevance],
                -item.published_at.timestamp(),
            )
        )
        return CuratedNews(
            ticker=ticker, source=news.source, items=tuple(curated_items[:_MAX_CURATED_RESULT])
        )

    async def _resolve_company_name(self, ticker: str, *, needed: bool) -> str | None:
        """Best-effort, non-fatal (task scope §5: "where reliable") —
        only attempted when enrichment might actually run (`needed`),
        so a ticker whose news is already fully cached never pays this
        extra lookup cost."""
        if not needed or self._search_use_case is None:
            return None
        try:
            results = await self._search_use_case.execute(ticker)
        except Exception:  # noqa: BLE001 - a resolver failure is never fatal here
            logger.info("news_intelligence operation=resolve_company_name ticker=%s status=failed", ticker)
            return None
        for result in results:
            if result.ticker == ticker:
                return result.name
        return None

    async def _enrich_and_persist(
        self, ticker: str, news_provider: str, to_enrich: list[InstrumentNewsItem]
    ) -> dict[str, PersistedNewsIntelligenceItem]:
        by_id = {item.id: item for item in to_enrich}
        candidates = tuple(
            NewsCandidateFact(
                id=item.id,
                headline=item.headline[:_MAX_HEADLINE_CHARS],
                summary=item.summary[:_MAX_SUMMARY_CHARS] if item.summary else None,
                source=item.source,
                published_at=item.published_at,
            )
            for item in to_enrich
        )
        assert self._ai_gateway is not None  # guarded by the caller (`to_enrich and self._ai_gateway is not None`)
        gateway = self._ai_gateway
        try:
            results = await gateway.generate_news_intelligence(ticker, candidates)
        except AINewsEnrichmentError as exc:
            logger.info(
                "news_intelligence operation=enrich_batch ticker=%s status=%s items_count=%d",
                ticker,
                type(exc).__name__,
                len(to_enrich),
            )
            return {}

        persisted: dict[str, PersistedNewsIntelligenceItem] = {}
        for result in results:
            source_item = by_id.get(result.id)
            if source_item is None:
                continue
            row = NewNewsIntelligenceRow(
                ticker=ticker,
                news_provider=news_provider,
                provider_news_id=source_item.id,
                headline_original=source_item.headline,
                source=source_item.source,
                published_at=source_item.published_at,
                url=source_item.url,
                enriched=True,
                summary_ru=result.summary_ru,
                why_it_matters=result.why_it_matters,
                relevance=result.relevance,
                relationship=result.relationship,
                impact_hypothesis=result.impact_hypothesis,
                llm_provider="xai",
                llm_model=gateway.model,
                llm_prompt_version=NEWS_PROMPT_VERSION,
                llm_schema_version=NEWS_SCHEMA_VERSION,
            )
            persisted[result.id] = await self._repository.add(row)
        return persisted

    def _to_curated_item(
        self, raw: InstrumentNewsItem, persisted: PersistedNewsIntelligenceItem | None
    ) -> CuratedNewsItem:
        if persisted is None:
            return CuratedNewsItem(
                id=raw.id,
                ticker=raw.ticker,
                headline=raw.headline,
                source=raw.source,
                published_at=raw.published_at,
                url=raw.url,
                summary=raw.summary,
                enriched=False,
                summary_ru=None,
                why_it_matters=None,
                relevance=None,
                relationship=None,
                impact_hypothesis=None,
            )
        return CuratedNewsItem(
            id=raw.id,
            ticker=raw.ticker,
            headline=raw.headline,
            source=raw.source,
            published_at=raw.published_at,
            url=raw.url,
            summary=raw.summary,
            enriched=True,
            summary_ru=persisted.summary_ru,
            why_it_matters=persisted.why_it_matters,
            relevance=persisted.relevance,
            relationship=persisted.relationship,
            impact_hypothesis=persisted.impact_hypothesis,
        )
