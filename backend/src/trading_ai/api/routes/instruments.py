"""Instrument details HTTP endpoint — thin transport layer only (ADR-0002, §17).

`GET /instruments/{ticker}` is a read-only market-data lookup for the
watchlist -> instrument-details navigation. It deliberately does not
depend on the database session/repository at all: unlike `/watchlist`,
this is not a combined persistence+market-data operation (task scope —
see `market_data.use_cases.GetInstrumentDetails`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading_ai.ai.gateway import XAIGateway
from trading_ai.ai.horizon import InvalidHorizonError, parse_horizon
from trading_ai.ai.pending_cache import PendingAnalysisCache
from trading_ai.ai.types import (
    AIAnalysisError,
    AIInsufficientDataError,
    AIRateLimitedError,
    AITimeoutError,
    AnalysisHorizon,
    ConfidenceLevel,
    DirectionalView,
    ForecastState,
)
from trading_ai.ai.use_cases import GenerateInstrumentAnalysis
from trading_ai.infrastructure.database.session import session_scope
from trading_ai.insights.domain import (
    MAX_HISTORY_ITEMS,
    InsightNotFoundError,
    PendingAnalysisNotFoundError,
    SavedInsight,
)
from trading_ai.insights.repository import InsightRepository
from trading_ai.insights.use_cases import (
    GetInsightDetail,
    ListInstrumentInsights,
    ListRecentInsights,
    SaveInsight,
)
from trading_ai.market_data.gateway import TwelveDataGateway
from trading_ai.market_data.news_gateway import FinnhubNewsGateway
from trading_ai.market_data.types import (
    InvalidPeriodError,
    InvalidSearchQueryError,
    MarketDataError,
    MarketDataRateLimitedError,
    MarketDataTimeoutError,
    TickerUnsupportedError,
)
from trading_ai.market_data.use_cases import (
    GetInstrumentDetails,
    GetInstrumentNews,
    GetInstrumentPriceHistory,
    SearchInstruments,
)
from trading_ai.news_intelligence.domain import CuratedNews, CuratedNewsItem
from trading_ai.news_intelligence.repository import NewsIntelligenceRepository
from trading_ai.news_intelligence.use_cases import GetNewsIntelligence

router = APIRouter()


class InstrumentDetailsResponse(BaseModel):
    """Transport DTO — provider-neutral, never Twelve Data's raw response shape.

    `open`/`high`/`low`/`previous_close`/`volume` are `None`, not a
    guessed `0`, whenever the provider's response didn't include or
    couldn't parse that field (see `gateway._optional_decimal`/
    `_optional_int`).
    """

    ticker: str
    price: Decimal
    change: Decimal
    change_percent: Decimal
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    previous_close: Decimal | None = None
    volume: int | None = None
    as_of: datetime
    source: str


class InstrumentSearchResultResponse(BaseModel):
    """Only the fields the UI actually needs — never Twelve Data's raw
    `/symbol_search` item shape (e.g. `mic_code`/`exchange_timezone`
    aren't carried, task scope §10: "search response не содержит
    лишних provider fields")."""

    ticker: str
    name: str
    exchange: str | None = None
    instrument_type: str | None = None
    currency: str | None = None


class InstrumentSearchResponse(BaseModel):
    """`items` is always capped at a fixed size (task scope §6:
    "максимум 10 результатов") — never provider-controlled pagination.
    An empty `items` list is a valid, non-error response."""

    query: str
    items: list[InstrumentSearchResultResponse]


class InstrumentHistoryPointResponse(BaseModel):
    """Phase 2B.1 (Professional Instrument Workspace, task scope §6):
    `open`/`high`/`low`/`volume` are additive, nullable fields exposing
    what `PricePoint`/`TwelveDataGateway._parse_history` already parses
    from the real provider response — confirmed live (this task's chart
    audit) as genuinely present per-bar for every point on the current
    plan, not fabricated. `None` only when the provider's own response
    didn't include/couldn't parse that specific field for that specific
    bar (same honest-nullability rule as `InstrumentDetailsResponse`),
    never a guessed value. `close` remains required — a bar without a
    usable close was already dropped upstream before this response is
    built."""

    timestamp: datetime
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal
    volume: int | None = None


class InstrumentHistoryResponse(BaseModel):
    """`points` is always chronological ASC (`gateway._parse_history`
    sorts defensively regardless of provider ordering) — never trust
    the caller to re-sort. An empty `points` list is a valid, non-error
    response (task scope §5: "пустой набор данных — контролируемый
    safe response")."""

    ticker: str
    period: str
    source: str
    points: list[InstrumentHistoryPointResponse]


class InstrumentNewsItemResponse(BaseModel):
    """Phase 2A (FR-064): additive extension over the original raw-news
    shape — `id`/`headline`/`source`/`published_at`/`url`/`summary`
    (the provider's own, untranslated summary) are unchanged from
    before this task; every field below is new and optional, so an
    older client reading only the original fields keeps working.

    `enriched=False` means the AI enrichment fields are all `None` —
    either the LLM gateway isn't configured, the batch call failed, or
    this specific item wasn't returned/validated by the model (task
    scope §16: graceful per-item/whole-response degradation, never a
    fabricated placeholder in place of a missing enrichment)."""

    id: str
    headline: str
    source: str
    published_at: datetime
    url: str
    summary: str | None = None
    enriched: bool = False
    summary_ru: str | None = None
    why_it_matters: str | None = None
    relevance: str | None = None
    relationship: str | None = None
    impact_hypothesis: str | None = None


class InstrumentNewsResponse(BaseModel):
    """`items` is now a *curated* set (Phase 2A, task scope §15): NOISE
    items are excluded, direct relevance is preferred, and the count is
    bounded independently of how many raw items the provider returned —
    an empty `items` list is a valid, non-error response meaning "no
    sufficiently relevant news," same as before this task."""

    ticker: str
    source: str
    items: list[InstrumentNewsItemResponse]


def _to_news_item_response(item: CuratedNewsItem) -> InstrumentNewsItemResponse:
    return InstrumentNewsItemResponse(
        id=item.id,
        headline=item.headline,
        source=item.source,
        published_at=item.published_at,
        url=item.url,
        summary=item.summary,
        enriched=item.enriched,
        summary_ru=item.summary_ru,
        why_it_matters=item.why_it_matters,
        relevance=item.relevance.value if item.relevance is not None else None,
        relationship=item.relationship.value if item.relationship is not None else None,
        impact_hypothesis=item.impact_hypothesis,
    )


class KeyFactResponse(BaseModel):
    """FR-011/FR-018 §2 — one fact plus a plain-language source label
    (never a full per-fact provenance record, see `ai/types.py`'s
    `KeyFact` docstring for why)."""

    fact: str
    source: str


class InstrumentAnalysisResponse(BaseModel):
    """Provider-neutral structured AI result covering FR-018's 10
    mandatory sections (task scope §4, §3 — see `ai/types.py`'s
    `InstrumentAnalysis` docstring for the exact section mapping).
    Never BUY/SELL/HOLD/target-price content — enforced by the
    gateway's fixed prompt plus local validation (`ai/gateway.py`), not
    just documented here. `disclaimer` is always the same fixed text.

    `analysis_token` is the *only* thing the client may send back to
    `POST /instruments/{ticker}/insights` to save this exact result —
    the client never resends analysis content itself (task scope §12).

    Phase 2B (Forecast Contract, FR-061/FR-062): fields from `horizon`
    onward are new, additive to the response shape above (task scope
    §7). `key_facts` doubles as the Forecast Contract's "evidence"
    field (`docs/architecture/FORECAST_CONTRACT.md` §3 explicitly maps
    "Ключевые факты" -> evidence) — not duplicated under a second field
    name. `directional_view`/`base_case`/`bullish_case`/`bearish_case`
    are `None` and `catalysts`/`invalidation_conditions` are empty
    whenever `forecast_state` is not `"forecast"` (task scope §12).
    """

    ticker: str
    generated_at: datetime
    summary: str
    price_context: str
    news_context: str
    key_facts: list[KeyFactResponse]
    insight_hypothesis: str
    confidence: ConfidenceLevel
    confidence_reason: str
    considerations: list[str]
    risks: list[str]
    key_drivers: list[str]
    data_freshness: str
    disclaimer: str
    source: str
    analysis_token: str
    horizon: AnalysisHorizon
    forecast_state: ForecastState
    directional_view: DirectionalView | None
    concise_verdict: str
    base_case: str | None
    bullish_case: str | None
    bearish_case: str | None
    catalysts: list[str]
    invalidation_conditions: list[str]
    what_to_watch_next: list[str]
    check_after: datetime
    uncertainty: str
    context_categories_used: list[str]


class InsightSummaryResponse(BaseModel):
    """Compact history-list item (task scope §14) — full content is
    fetched on demand via `GET /insights/{id}`, not embedded here, to
    keep the list payload small.

    Phase 2B (task scope §17): `horizon`/`forecast_state`/
    `directional_view`/`concise_verdict` let the history list show a
    forecast insight's verdict at a glance without a second fetch —
    all four `None` for a pre-Phase-2B row (`schema_version ==
    "insight-structure-v1"`), same optionality as everywhere else.
    """

    id: int
    ticker: str
    generated_at: datetime
    created_at: datetime
    confidence: ConfidenceLevel
    summary: str
    horizon: AnalysisHorizon | None = None
    forecast_state: ForecastState | None = None
    directional_view: DirectionalView | None = None
    concise_verdict: str | None = None


class InstrumentInsightsResponse(BaseModel):
    ticker: str
    items: list[InsightSummaryResponse]


class RecentInsightsResponse(BaseModel):
    """Cross-ticker equivalent of `InstrumentInsightsResponse` (Phase 1,
    Insights/History area) — no top-level `ticker`, since each item
    already carries its own (`InsightSummaryResponse.ticker`)."""

    items: list[InsightSummaryResponse]


class InsightDetailResponse(BaseModel):
    """Full persisted insight — returned by both the save endpoint and
    `GET /insights/{id}`.

    Phase 2B: fields from `horizon` onward are all `None`/`[]` for a
    row saved before this task — a client checks `horizon is not null`
    to know whether to render the Forecast Contract block at all (task
    scope §17: "old saved insights must still render")."""

    id: int
    ticker: str
    generated_at: datetime
    created_at: datetime
    summary: str
    price_context: str
    news_context: str
    key_facts: list[KeyFactResponse]
    insight_hypothesis: str
    confidence: ConfidenceLevel
    confidence_reason: str
    considerations: list[str]
    risks: list[str]
    key_drivers: list[str]
    data_freshness: str
    disclaimer: str
    provider: str
    model: str
    prompt_version: str
    schema_version: str
    horizon: AnalysisHorizon | None = None
    forecast_state: ForecastState | None = None
    directional_view: DirectionalView | None = None
    concise_verdict: str | None = None
    base_case: str | None = None
    bullish_case: str | None = None
    bearish_case: str | None = None
    catalysts: list[str] = []
    invalidation_conditions: list[str] = []
    what_to_watch_next: list[str] = []
    check_after: datetime | None = None
    uncertainty: str | None = None
    context_categories_used: list[str] = []


class SaveInsightRequest(BaseModel):
    """The *only* field the save endpoint accepts — no analysis content
    (task scope §12: "не позволять frontend подделать
    provider/model/provenance"). `extra="forbid"` so a client that
    mistakenly (or deliberately) sends e.g. `provider`/`summary` gets an
    explicit 422 instead of those fields being silently dropped — even
    though the use case never reads anything but `analysis_token` from
    this body either way."""

    model_config = ConfigDict(extra="forbid")

    analysis_token: str


def _to_insight_summary_response(insight: SavedInsight) -> InsightSummaryResponse:
    return InsightSummaryResponse(
        id=insight.id,
        ticker=insight.ticker,
        generated_at=insight.generated_at,
        created_at=insight.created_at,
        confidence=insight.confidence,
        summary=insight.summary,
        horizon=insight.horizon,
        forecast_state=insight.forecast_state,
        directional_view=insight.directional_view,
        concise_verdict=insight.concise_verdict,
    )


def _to_insight_detail_response(insight: SavedInsight) -> InsightDetailResponse:
    return InsightDetailResponse(
        id=insight.id,
        ticker=insight.ticker,
        generated_at=insight.generated_at,
        created_at=insight.created_at,
        summary=insight.summary,
        price_context=insight.price_context,
        news_context=insight.news_context,
        key_facts=[
            KeyFactResponse(fact=fact.fact, source=fact.source) for fact in insight.key_facts
        ],
        insight_hypothesis=insight.insight_hypothesis,
        confidence=insight.confidence,
        confidence_reason=insight.confidence_reason,
        considerations=list(insight.considerations),
        risks=list(insight.risks),
        key_drivers=list(insight.key_drivers),
        data_freshness=insight.data_freshness,
        disclaimer=insight.disclaimer,
        provider=insight.provider,
        model=insight.model,
        prompt_version=insight.prompt_version,
        schema_version=insight.schema_version,
        horizon=insight.horizon,
        forecast_state=insight.forecast_state,
        directional_view=insight.directional_view,
        concise_verdict=insight.concise_verdict,
        base_case=insight.base_case,
        bullish_case=insight.bullish_case,
        bearish_case=insight.bearish_case,
        catalysts=list(insight.catalysts),
        invalidation_conditions=list(insight.invalidation_conditions),
        what_to_watch_next=list(insight.what_to_watch_next),
        check_after=insight.check_after,
        uncertainty=insight.uncertainty,
        context_categories_used=list(insight.context_categories_used),
    )


def get_market_data_gateway(request: Request) -> TwelveDataGateway:
    """Return the gateway created by the lifespan, or fail controlled.

    Duplicated (not imported) from `api.routes.watchlist`: this route
    module has no other reason to depend on the watchlist route module,
    and the dependency itself is a few lines reading `app.state`.
    """
    gateway = getattr(request.app.state, "market_data_gateway", None)
    if gateway is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="market data is not configured",
        )
    return gateway  # type: ignore[no-any-return]


def get_instrument_details_use_case(
    gateway: Annotated[TwelveDataGateway, Depends(get_market_data_gateway)],
) -> GetInstrumentDetails:
    return GetInstrumentDetails(gateway)


def get_instrument_price_history_use_case(
    gateway: Annotated[TwelveDataGateway, Depends(get_market_data_gateway)],
) -> GetInstrumentPriceHistory:
    return GetInstrumentPriceHistory(gateway)


def get_search_instruments_use_case(
    gateway: Annotated[TwelveDataGateway, Depends(get_market_data_gateway)],
) -> SearchInstruments:
    return SearchInstruments(gateway)


def get_news_gateway(request: Request) -> FinnhubNewsGateway:
    """Same optional-feature pattern as `get_market_data_gateway`, a
    separate provider/secret (`TRADING_AI_NEWS_API_KEY` -> Finnhub)."""
    gateway = getattr(request.app.state, "news_gateway", None)
    if gateway is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="news is not configured",
        )
    return gateway  # type: ignore[no-any-return]


def get_instrument_news_use_case(
    gateway: Annotated[FinnhubNewsGateway, Depends(get_news_gateway)],
) -> GetInstrumentNews:
    return GetInstrumentNews(gateway)


def get_optional_news_gateway(request: Request) -> FinnhubNewsGateway | None:
    """Unlike `get_news_gateway`, never raises.

    The AI-analysis endpoint degrades gracefully when news isn't
    configured at all (task scope §9) — same treatment as a
    configured-but-failing news call, not a hard failure of the whole
    analysis over one optional data source.
    """
    gateway = getattr(request.app.state, "news_gateway", None)
    return gateway


def get_ai_gateway(request: Request) -> XAIGateway:
    """Same optional-feature pattern as `get_market_data_gateway`, a
    third separate provider/secret (`TRADING_AI_LLM_API_KEY` -> xAI)."""
    gateway = getattr(request.app.state, "ai_gateway", None)
    if gateway is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI analysis is not configured",
        )
    return gateway  # type: ignore[no-any-return]


def get_optional_ai_gateway(request: Request) -> XAIGateway | None:
    """Unlike `get_ai_gateway`, never raises.

    News enrichment degrades gracefully when the LLM gateway isn't
    configured at all (Phase 2A, task scope §16) — the raw, curated
    (deterministic-only) news feed remains usable; only the AI
    enrichment fields are absent. Same optional pattern as
    `get_optional_news_gateway` above.
    """
    gateway = getattr(request.app.state, "ai_gateway", None)
    return gateway


def get_generate_instrument_analysis_use_case(
    ai_gateway: Annotated[XAIGateway, Depends(get_ai_gateway)],
    market_gateway: Annotated[TwelveDataGateway, Depends(get_market_data_gateway)],
    optional_news_gateway: Annotated[
        FinnhubNewsGateway | None, Depends(get_optional_news_gateway)
    ],
) -> GenerateInstrumentAnalysis:
    news_use_case = (
        GetInstrumentNews(optional_news_gateway) if optional_news_gateway is not None else None
    )
    return GenerateInstrumentAnalysis(
        details_use_case=GetInstrumentDetails(market_gateway),
        history_use_case=GetInstrumentPriceHistory(market_gateway),
        news_use_case=news_use_case,
        ai_gateway=ai_gateway,
    )


def get_pending_analysis_cache(request: Request) -> PendingAnalysisCache:
    """Unlike the provider gateways above, this is never optional/None —
    it's plain in-process memory (`ai/pending_cache.py`), created
    unconditionally in `main.py`'s lifespan regardless of which secrets
    are configured. Self-healing (not a hard `AttributeError`) for the
    case where a caller built the app without running the lifespan at
    all (e.g. a test using a bare `TestClient(app)` instead of `with
    TestClient(app) as client:`) — a fresh, empty cache is a safe
    fallback since it's just memory, never a secret/external resource.
    """
    cache: PendingAnalysisCache | None = getattr(request.app.state, "pending_analysis_cache", None)
    if cache is None:
        cache = PendingAnalysisCache()
        request.app.state.pending_analysis_cache = cache
    return cache


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    """Duplicated (not imported) from `api.routes.watchlist` — same
    reasoning as `get_market_data_gateway` above: this route module has
    no other reason to depend on the watchlist route module."""
    factory = getattr(request.app.state, "db_session_factory", None)
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database is not configured",
        )
    return factory  # type: ignore[no-any-return]


async def get_db_session(
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> AsyncIterator[AsyncSession]:
    """One session per request, one short transaction — same pattern as
    `api.routes.watchlist.get_db_session`."""
    async with session_scope(factory) as session:
        yield session


def get_insight_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> InsightRepository:
    return InsightRepository(session)


def get_news_intelligence_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> NewsIntelligenceRepository:
    """Phase 2A: unlike the raw-news lookup before this task, the
    curated/enriched news endpoint now requires a database connection
    (same hard-dependency pattern as `insights`/`journal`/`evaluations`)
    — it is the persisted reuse cache (task scope §10), not optional
    decoration. `GET /instruments/{ticker}/news` reports 503 when the
    database isn't configured, a real, documented behavior change from
    before this task (see the Phase 2A final report)."""
    return NewsIntelligenceRepository(session)


def get_news_intelligence_use_case(
    news_use_case: Annotated[GetInstrumentNews, Depends(get_instrument_news_use_case)],
    repository: Annotated[NewsIntelligenceRepository, Depends(get_news_intelligence_repository)],
    optional_ai_gateway: Annotated[XAIGateway | None, Depends(get_optional_ai_gateway)],
    search_use_case: Annotated[SearchInstruments, Depends(get_search_instruments_use_case)],
) -> GetNewsIntelligence:
    return GetNewsIntelligence(
        news_use_case=news_use_case,
        repository=repository,
        ai_gateway=optional_ai_gateway,
        search_use_case=search_use_case,
    )


def get_save_insight_use_case(
    repository: Annotated[InsightRepository, Depends(get_insight_repository)],
    pending_cache: Annotated[PendingAnalysisCache, Depends(get_pending_analysis_cache)],
) -> SaveInsight:
    return SaveInsight(repository, pending_cache)


def get_list_instrument_insights_use_case(
    repository: Annotated[InsightRepository, Depends(get_insight_repository)],
) -> ListInstrumentInsights:
    return ListInstrumentInsights(repository)


def get_insight_detail_use_case(
    repository: Annotated[InsightRepository, Depends(get_insight_repository)],
) -> GetInsightDetail:
    return GetInsightDetail(repository)


def get_list_recent_insights_use_case(
    repository: Annotated[InsightRepository, Depends(get_insight_repository)],
) -> ListRecentInsights:
    return ListRecentInsights(repository)


@router.get("/instruments/search", response_model=InstrumentSearchResponse)
async def search_instruments(
    q: str,
    use_case: Annotated[SearchInstruments, Depends(get_search_instruments_use_case)],
) -> InstrumentSearchResponse:
    """Registered *before* `GET /instruments/{ticker}` below — Starlette
    matches routes in registration order, and `/instruments/{ticker}`
    would otherwise swallow `/instruments/search` requests as
    `ticker="search"` (task scope §6: a clean, unambiguous REST
    contract)."""
    results = await use_case.execute(q)
    return InstrumentSearchResponse(
        query=q.strip(),
        items=[
            InstrumentSearchResultResponse(
                ticker=result.ticker,
                name=result.name,
                exchange=result.exchange,
                instrument_type=result.instrument_type,
                currency=result.currency,
            )
            for result in results
        ],
    )


@router.get("/instruments/{ticker}", response_model=InstrumentDetailsResponse)
async def get_instrument_details(
    ticker: str,
    use_case: Annotated[GetInstrumentDetails, Depends(get_instrument_details_use_case)],
) -> InstrumentDetailsResponse:
    snapshot = await use_case.execute(ticker)
    return InstrumentDetailsResponse(
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
        source=snapshot.source,
    )


@router.get("/instruments/{ticker}/history", response_model=InstrumentHistoryResponse)
async def get_instrument_price_history(
    ticker: str,
    period: str,
    use_case: Annotated[
        GetInstrumentPriceHistory, Depends(get_instrument_price_history_use_case)
    ],
) -> InstrumentHistoryResponse:
    history = await use_case.execute(ticker, period)
    return InstrumentHistoryResponse(
        ticker=history.ticker,
        period=history.period.value,
        source=history.source,
        points=[
            InstrumentHistoryPointResponse(
                timestamp=point.timestamp,
                open=point.open,
                high=point.high,
                low=point.low,
                close=point.close,
                volume=point.volume,
            )
            for point in history.points
        ],
    )


@router.get("/instruments/{ticker}/news", response_model=InstrumentNewsResponse)
async def get_instrument_news(
    ticker: str,
    use_case: Annotated[GetNewsIntelligence, Depends(get_news_intelligence_use_case)],
) -> InstrumentNewsResponse:
    """Phase 2A (FR-064, UJ-034): returns a curated, classified,
    Russian-summarized news feed instead of a raw pass-through of the
    provider's items — see `GetNewsIntelligence` for the full pipeline
    (dedup, cache reuse, LLM enrichment, curation). Still degrades to a
    deterministic-only curated list (all `enriched=False`) when the LLM
    gateway is unavailable, and still reports the provider's own
    404/503/504 errors unchanged when Finnhub itself fails — only the
    *content* of a successful response has changed (task scope §13)."""
    news: CuratedNews = await use_case.execute(ticker)
    return InstrumentNewsResponse(
        ticker=news.ticker,
        source=news.source,
        items=[_to_news_item_response(item) for item in news.items],
    )


@router.post("/instruments/{ticker}/analysis", response_model=InstrumentAnalysisResponse)
async def generate_instrument_analysis(
    ticker: str,
    use_case: Annotated[
        GenerateInstrumentAnalysis, Depends(get_generate_instrument_analysis_use_case)
    ],
    pending_cache: Annotated[PendingAnalysisCache, Depends(get_pending_analysis_cache)],
    horizon: Annotated[
        str,
        Query(
            description="SHORT (1-5 trading days) / MEDIUM (~1-8 weeks) / LONG (~2-12 months) — FR-006."
        ),
    ],
) -> InstrumentAnalysisResponse:
    """No request body is accepted — the ticker comes from the path,
    the horizon from a required query parameter (task scope §6: the
    endpoint never accepts a free-form prompt; task scope §4/FR-006:
    horizon is never silently defaulted — its absence is a `422`, the
    same as an unparseable value, via `InvalidHorizonError`/FastAPI's
    own required-query-param validation). POST, not GET, since this
    triggers a paid/computational LLM generation call rather than a
    cached-feeling read (task scope §10).

    Generation and persistence are decoupled (Product Owner decision,
    task scope §2: explicit "Сохранить инсайт" action, not auto-save).
    This endpoint never writes to the database — it only stashes the
    result in the in-process `pending_cache` under a fresh token, which
    the client must present back to `POST /instruments/{ticker}/insights`
    to actually save it.
    """
    parsed_horizon = parse_horizon(horizon)
    analysis = await use_case.execute(ticker, parsed_horizon)
    analysis_token = pending_cache.put(analysis.ticker, analysis)
    assert analysis.horizon is not None
    assert analysis.forecast_state is not None
    assert analysis.check_after is not None
    return InstrumentAnalysisResponse(
        ticker=analysis.ticker,
        generated_at=analysis.generated_at,
        summary=analysis.summary,
        price_context=analysis.price_context,
        news_context=analysis.news_context,
        key_facts=[
            KeyFactResponse(fact=fact.fact, source=fact.source) for fact in analysis.key_facts
        ],
        insight_hypothesis=analysis.insight_hypothesis,
        confidence=analysis.confidence,
        confidence_reason=analysis.confidence_reason,
        considerations=list(analysis.considerations),
        risks=list(analysis.risks),
        key_drivers=list(analysis.key_drivers),
        data_freshness=analysis.data_freshness,
        disclaimer=analysis.disclaimer,
        source=analysis.provider,
        analysis_token=analysis_token,
        horizon=analysis.horizon,
        forecast_state=analysis.forecast_state,
        directional_view=analysis.directional_view,
        concise_verdict=analysis.concise_verdict or "",
        base_case=analysis.base_case,
        bullish_case=analysis.bullish_case,
        bearish_case=analysis.bearish_case,
        catalysts=list(analysis.catalysts),
        invalidation_conditions=list(analysis.invalidation_conditions),
        what_to_watch_next=list(analysis.what_to_watch_next),
        check_after=analysis.check_after,
        uncertainty=analysis.uncertainty or "",
        context_categories_used=list(analysis.context_categories_used),
    )


@router.post(
    "/instruments/{ticker}/insights",
    response_model=InsightDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def save_insight(
    ticker: str,
    payload: SaveInsightRequest,
    use_case: Annotated[SaveInsight, Depends(get_save_insight_use_case)],
) -> InsightDetailResponse:
    """Persists exactly the server-held analysis identified by
    `analysis_token` — the request body carries no analysis content
    (task scope §12)."""
    insight = await use_case.execute(ticker, payload.analysis_token)
    return _to_insight_detail_response(insight)


@router.get("/instruments/{ticker}/insights", response_model=InstrumentInsightsResponse)
async def list_instrument_insights(
    ticker: str,
    use_case: Annotated[ListInstrumentInsights, Depends(get_list_instrument_insights_use_case)],
) -> InstrumentInsightsResponse:
    """Newest-first, bounded history (task scope §14) — compact items
    only, see `InsightSummaryResponse`."""
    insights = await use_case.execute(ticker)
    return InstrumentInsightsResponse(
        ticker=insights[0].ticker if insights else ticker.strip().upper(),
        items=[_to_insight_summary_response(insight) for insight in insights],
    )


@router.get("/insights", response_model=RecentInsightsResponse)
async def list_recent_insights(
    use_case: Annotated[ListRecentInsights, Depends(get_list_recent_insights_use_case)],
    limit: Annotated[int, Query(ge=1, le=MAX_HISTORY_ITEMS)] = MAX_HISTORY_ITEMS,
) -> RecentInsightsResponse:
    """Cross-ticker, newest-first, bounded (Phase 1, Insights/History
    area) — registered before `GET /insights/{insight_id}` is irrelevant
    here (different segment counts, no routing ambiguity), but kept next
    to it for readability. Read-only: no mutation, no new persistence
    concept, reuses the existing `insights` module end-to-end."""
    insights = await use_case.execute(limit)
    return RecentInsightsResponse(items=[_to_insight_summary_response(item) for item in insights])


@router.get("/insights/{insight_id}", response_model=InsightDetailResponse)
async def get_insight_detail(
    insight_id: int,
    use_case: Annotated[GetInsightDetail, Depends(get_insight_detail_use_case)],
) -> InsightDetailResponse:
    insight = await use_case.execute(insight_id)
    return _to_insight_detail_response(insight)


def register_ai_analysis_exception_handlers(app: FastAPI) -> None:
    """Map AI-analysis errors to safe, controlled HTTP responses.

    `InvalidTickerError` (raised by `normalize_ticker` inside the use
    case) is already handled globally by
    `register_watchlist_exception_handlers` (422). Same MRO-based
    dispatch pattern as `register_instruments_exception_handlers`: the
    `AIAnalysisError` base-class handler is the fallback for
    `AIProviderUnavailableError`/`AIInvalidOutputError`, which don't
    need a more specific status code than 503.
    """

    @app.exception_handler(AIInsufficientDataError)
    async def _handle_insufficient_data(
        _request: Request, _exc: AIInsufficientDataError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "insufficient data to generate an analysis"},
        )

    @app.exception_handler(AIRateLimitedError)
    async def _handle_ai_rate_limited(_request: Request, _exc: AIRateLimitedError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "AI provider is rate limited"},
        )

    @app.exception_handler(AITimeoutError)
    async def _handle_ai_timeout(_request: Request, _exc: AITimeoutError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content={"detail": "AI provider timed out"},
        )

    @app.exception_handler(AIAnalysisError)
    async def _handle_ai_analysis_error(_request: Request, _exc: AIAnalysisError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "AI analysis is unavailable"},
        )


def register_insight_exception_handlers(app: FastAPI) -> None:
    """Map insight-persistence errors to safe, controlled HTTP responses.

    `InvalidTickerError` is already handled globally (422, see above).
    Database errors surface as a plain 503 through
    `get_session_factory`'s `HTTPException` (same pattern as
    `api.routes.watchlist`) — no SQL detail ever reaches this layer.
    """

    @app.exception_handler(PendingAnalysisNotFoundError)
    async def _handle_pending_analysis_not_found(
        _request: Request, _exc: PendingAnalysisNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "detail": "no pending AI analysis to save for this ticker — "
                "generate one first, then save it within 30 minutes"
            },
        )

    @app.exception_handler(InsightNotFoundError)
    async def _handle_insight_not_found(
        _request: Request, _exc: InsightNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "insight not found"},
        )


def register_instruments_exception_handlers(app: FastAPI) -> None:
    """Map market-data errors to safe, controlled HTTP responses.

    `InvalidTickerError` (raised by `normalize_ticker` inside the use
    case) is already handled globally by
    `register_watchlist_exception_handlers` (422) — not duplicated
    here, since FastAPI exception handlers apply app-wide, not per
    router.

    Starlette dispatches on `type(exc).__mro__`, most specific first:
    `TickerUnsupportedError`/`MarketDataRateLimitedError`/
    `MarketDataTimeoutError` get their own status codes below, and the
    `MarketDataError` base-class handler is the fallback for the two
    subclasses that don't need a more specific one
    (`MarketDataUnavailableError`, `MarketDataMalformedResponseError`)
    — both are safely a 503, never the raw provider/exception detail.
    """

    @app.exception_handler(InvalidPeriodError)
    async def _handle_invalid_period(_request: Request, exc: InvalidPeriodError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.reason},
        )

    @app.exception_handler(InvalidHorizonError)
    async def _handle_invalid_horizon(_request: Request, exc: InvalidHorizonError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.reason},
        )

    @app.exception_handler(InvalidSearchQueryError)
    async def _handle_invalid_search_query(
        _request: Request, exc: InvalidSearchQueryError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.reason},
        )

    @app.exception_handler(TickerUnsupportedError)
    async def _handle_ticker_unsupported(
        _request: Request, _exc: TickerUnsupportedError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "instrument not found"},
        )

    @app.exception_handler(MarketDataRateLimitedError)
    async def _handle_rate_limited(
        _request: Request, _exc: MarketDataRateLimitedError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "market data provider is rate limited"},
        )

    @app.exception_handler(MarketDataTimeoutError)
    async def _handle_timeout(_request: Request, _exc: MarketDataTimeoutError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content={"detail": "market data provider timed out"},
        )

    @app.exception_handler(MarketDataError)
    async def _handle_market_data_error(_request: Request, _exc: MarketDataError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "market data provider is unavailable"},
        )
