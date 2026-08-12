/**
 * Typed client for `GET /instruments/{ticker}`
 * (see `backend/src/trading_ai/api/routes/instruments.py`). Separate
 * from `watchlist-api.ts`: instrument details is a standalone,
 * read-only market-data lookup, not a watchlist operation — no
 * generic HTTP client abstraction, just the one function this page
 * needs (ADR-0003, §22.2).
 *
 * Numeric fields arrive as JSON strings (backend `Decimal`) and are
 * parsed with `Number()` only for display, never for further
 * arithmetic here. `open`/`high`/`low`/`previous_close`/`volume` are
 * honestly nullable: the backend sends `null`, never a guessed `0`,
 * when Twelve Data's response didn't include that field — this client
 * must not paper over that with a default value either.
 */

const DEFAULT_DEV_API_BASE_URL = "http://127.0.0.1:8000";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_DEV_API_BASE_URL;

export interface InstrumentDetails {
  ticker: string;
  price: string;
  change: string;
  change_percent: string;
  open: string | null;
  high: string | null;
  low: string | null;
  previous_close: string | null;
  volume: number | null;
  as_of: string;
  source: string;
}

/**
 * Fixed chart-period contract shared with the backend
 * (`trading_ai.market_data.types.InstrumentHistoryPeriod`) — never a
 * raw Twelve Data `interval`/`outputsize` pair (ADR-0007 §20-22-style
 * provider boundary, applied here to the market-data gateway too).
 */
export type InstrumentHistoryPeriod = "1D" | "5D" | "1M";

export interface InstrumentHistoryPoint {
  timestamp: string;
  /** Backend `Decimal`, serialized as a string — see `InstrumentDetails.price`. */
  close: string;
}

export interface InstrumentPriceHistory {
  ticker: string;
  period: InstrumentHistoryPeriod;
  source: string;
  /** Always chronological ASC — the backend sorts defensively regardless of provider order. */
  points: InstrumentHistoryPoint[];
}

/** FR-064 — a categorical relevance level, never a fabricated numeric score. */
export type NewsRelevance = "high" | "medium" | "low";

/**
 * FR-064 — how a news item relates to the instrument it was fetched
 * for. `noise` items are already excluded server-side (`GetNewsIntelligence`)
 * — this client should never need to filter them out again, but the
 * type exists because a raw/unenriched item's `relationship` is `null`,
 * not because `noise` is expected to appear here.
 */
export type NewsRelationship = "company" | "sector" | "market" | "macro" | "indirect" | "noise";

export interface InstrumentNewsItem {
  id: string;
  headline: string;
  source: string;
  published_at: string;
  url: string;
  /** The provider's own, untranslated summary — `null`, never an
   * invented placeholder, when the provider didn't return one. */
  summary: string | null;
  /**
   * Phase 2A (FR-064): `false` means the AI enrichment fields below are
   * all `null` — either the LLM gateway isn't configured, the batch
   * enrichment call failed, or this specific item wasn't returned by
   * the model. Never a fabricated placeholder in place of a missing
   * enrichment — the UI must show a plainer card, not invent content.
   */
  enriched: boolean;
  /** Concise Russian summary — materially shorter than `summary`/`headline`. */
  summary_ru: string | null;
  why_it_matters: string | null;
  relevance: NewsRelevance | null;
  relationship: NewsRelationship | null;
  /** Always an explicit hypothesis, never a prediction — the UI must
   * label it as such, the string itself is not guaranteed to contain
   * hedging language verbatim. */
  impact_hypothesis: string | null;
}

export interface InstrumentNewsResponse {
  ticker: string;
  source: string;
  /**
   * Phase 2A: a *curated* set — NOISE items excluded, direct relevance
   * preferred, bounded independently of how many raw items the
   * provider returned. An empty list means "no sufficiently relevant
   * news," a valid, non-error state (task scope §15).
   */
  items: InstrumentNewsItem[];
}

/** FR-011/FR-018 §2 — one fact plus a plain-language source label (not
 * a full per-fact provenance record, see backend `ai/types.py`'s
 * `KeyFact` docstring for why). */
export interface InstrumentKeyFact {
  fact: string;
  source: string;
}

/** FR-019 — a documented categorical level, never a fabricated numeric
 * score (e.g. "83.7%"). */
export type InstrumentConfidenceLevel = "high" | "medium" | "low";

/** FR-006 — the three Product-Owner-approved analysis horizons
 * (Phase 2.0, PO-2.0-3). Selected by the user before generation, never
 * defaulted by this client (task scope §4). */
export type AnalysisHorizon = "short" | "medium" | "long";

/** PO-2.0-4 — a fixed categorical directional scale, never
 * BUY/SELL/HOLD (no execution command). */
export type DirectionalView =
  | "strongly_bullish"
  | "bullish"
  | "neutral"
  | "bearish"
  | "strongly_bearish";

/**
 * `FORECAST_CONTRACT.md` §5, PO-2.0-8 — `no_quality_setup`/
 * `insufficient_edge`/`insufficient_data` are valid, desired outcomes,
 * never a fallback for a failed request. The UI must show these states
 * plainly, never force a directional-looking card over them.
 */
export type ForecastState = "forecast" | "no_quality_setup" | "insufficient_edge" | "insufficient_data";

/**
 * FR-018's 10 mandatory insight sections (see backend `ai/types.py`'s
 * `InstrumentAnalysis` docstring for the exact section mapping).
 * `analysis_token` is the *only* thing that may be sent back to
 * `saveInsight` — this client never re-sends analysis content itself
 * (backend task scope §12: the save endpoint never trusts client-
 * supplied provenance).
 *
 * Phase 2B (Forecast Contract, FR-061/FR-062): fields from `horizon`
 * onward are new, additive to the response shape above. `key_facts`
 * doubles as the Forecast Contract's "evidence" field (`docs/
 * architecture/FORECAST_CONTRACT.md` §3) — not duplicated under a
 * second field name. `directional_view`/`base_case`/`bullish_case`/
 * `bearish_case` are `null` and `catalysts`/`invalidation_conditions`
 * are empty whenever `forecast_state` is not `"forecast"`.
 */
export interface InstrumentAiAnalysis {
  ticker: string;
  generated_at: string;
  summary: string;
  price_context: string;
  news_context: string;
  key_facts: InstrumentKeyFact[];
  insight_hypothesis: string;
  confidence: InstrumentConfidenceLevel;
  confidence_reason: string;
  considerations: string[];
  risks: string[];
  key_drivers: string[];
  data_freshness: string;
  disclaimer: string;
  source: string;
  analysis_token: string;
  horizon: AnalysisHorizon;
  forecast_state: ForecastState;
  directional_view: DirectionalView | null;
  concise_verdict: string;
  base_case: string | null;
  bullish_case: string | null;
  bearish_case: string | null;
  catalysts: string[];
  invalidation_conditions: string[];
  what_to_watch_next: string[];
  check_after: string;
  uncertainty: string;
  context_categories_used: string[];
}

/** Compact history-list item — full content is fetched on demand via
 * `getInsightDetail`, not embedded here (task scope §14).
 *
 * Phase 2B (task scope §17): `horizon`/`forecast_state`/
 * `directional_view`/`concise_verdict` let the history list show a
 * forecast insight's verdict at a glance — all four `null` for a
 * pre-Phase-2B row.
 */
export interface InsightSummary {
  id: number;
  ticker: string;
  generated_at: string;
  created_at: string;
  confidence: InstrumentConfidenceLevel;
  summary: string;
  horizon: AnalysisHorizon | null;
  forecast_state: ForecastState | null;
  directional_view: DirectionalView | null;
  concise_verdict: string | null;
}

export interface InstrumentInsightsResponse {
  ticker: string;
  /** Newest-first, bounded — never infinite-scroll pagination. */
  items: InsightSummary[];
}

/** Cross-ticker equivalent of `InstrumentInsightsResponse` (Phase 1,
 * Insights/History area) — no top-level `ticker`, since each item
 * already carries its own (`InsightSummary.ticker`). */
export interface RecentInsightsResponse {
  items: InsightSummary[];
}

/** Full persisted insight — returned by both `saveInsight` and
 * `getInsightDetail`.
 *
 * Phase 2B: fields from `horizon` onward are all `null`/`[]` for a row
 * saved before this task — a component checks `horizon !== null` to
 * know whether to render the Forecast Contract block at all (task
 * scope §17: "old saved insights must still render"). */
export interface InsightDetail {
  id: number;
  ticker: string;
  generated_at: string;
  created_at: string;
  summary: string;
  price_context: string;
  news_context: string;
  key_facts: InstrumentKeyFact[];
  insight_hypothesis: string;
  confidence: InstrumentConfidenceLevel;
  confidence_reason: string;
  considerations: string[];
  risks: string[];
  key_drivers: string[];
  data_freshness: string;
  disclaimer: string;
  provider: string;
  model: string;
  prompt_version: string;
  schema_version: string;
  horizon: AnalysisHorizon | null;
  forecast_state: ForecastState | null;
  directional_view: DirectionalView | null;
  concise_verdict: string | null;
  base_case: string | null;
  bullish_case: string | null;
  bearish_case: string | null;
  catalysts: string[];
  invalidation_conditions: string[];
  what_to_watch_next: string[];
  check_after: string | null;
  uncertainty: string | null;
  context_categories_used: string[];
}

/**
 * FR-035 — Product Owner decision: categorical 3-way, not binary, not
 * numeric (a small numeric scale was rejected as implying a precision
 * no single glance at a saved insight can support, same reasoning
 * `InstrumentConfidenceLevel` used for confidence).
 */
export type InsightRating = "useful" | "partially_useful" | "not_useful";

/**
 * The evaluation/outcome record for one saved insight
 * (`trading_ai.evaluations` — **not** the developer AI quality harness).
 * One record per insight; either half may be `null` until the user acts
 * on it (FR-035 rating, FR-036/038 manual outcome).
 */
export interface InsightEvaluation {
  insight_id: number;
  rating: InsightRating | null;
  rated_at: string | null;
  outcome_note: string | null;
  outcome_recorded_at: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface InstrumentSearchResult {
  ticker: string;
  name: string;
  exchange: string | null;
  instrument_type: string | null;
  currency: string | null;
}

export interface InstrumentSearchResponse {
  query: string;
  /** Always capped at a fixed size — never provider-controlled pagination. */
  items: InstrumentSearchResult[];
}

export type InstrumentApiErrorKind =
  | "invalid"
  | "not-found"
  | "timeout"
  | "unavailable"
  | "network"
  | "unexpected";

/** Thrown by `getInstrumentDetails` — always has a Russian, user-safe `message`. */
export class InstrumentApiError extends Error {
  readonly kind: InstrumentApiErrorKind;
  /** Raw backend `detail`, if any — for developer diagnostics only, never rendered. */
  readonly backendDetail?: string;

  constructor(kind: InstrumentApiErrorKind, message: string, backendDetail?: string) {
    super(message);
    this.name = "InstrumentApiError";
    this.kind = kind;
    this.backendDetail = backendDetail;
  }
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isInstrumentDetails(value: unknown): value is InstrumentDetails {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.ticker === "string" &&
    typeof candidate.price === "string" &&
    typeof candidate.change === "string" &&
    typeof candidate.change_percent === "string" &&
    isNullableString(candidate.open) &&
    isNullableString(candidate.high) &&
    isNullableString(candidate.low) &&
    isNullableString(candidate.previous_close) &&
    (candidate.volume === null || typeof candidate.volume === "number") &&
    typeof candidate.as_of === "string" &&
    typeof candidate.source === "string"
  );
}

/** Safely extract `{"detail": "..."}` from an error response, without trusting its shape. */
async function readBackendDetail(response: Response): Promise<string | undefined> {
  try {
    const data: unknown = await response.json();
    if (
      typeof data === "object" &&
      data !== null &&
      typeof (data as Record<string, unknown>).detail === "string"
    ) {
      return (data as Record<string, unknown>).detail as string;
    }
  } catch {
    // Not JSON (e.g. an HTML proxy error page) — no detail available,
    // and that raw body is never shown to the user either way.
  }
  return undefined;
}

export async function getInstrumentDetails(ticker: string): Promise<InstrumentDetails> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/instruments/${encodeURIComponent(ticker)}`, {
      method: "GET",
      // Always the current price, never a stale cached one shown as fresh.
      cache: "no-store",
    });
  } catch {
    throw new InstrumentApiError(
      "network",
      "Не удалось соединиться с сервером. Проверьте, что backend запущен, и повторите попытку."
    );
  }

  if (response.status === 422) {
    throw new InstrumentApiError(
      "invalid",
      "Некорректный тикер.",
      await readBackendDetail(response)
    );
  }

  if (response.status === 404) {
    throw new InstrumentApiError(
      "not-found",
      "Инструмент не найден.",
      await readBackendDetail(response)
    );
  }

  if (response.status === 504) {
    throw new InstrumentApiError(
      "timeout",
      "Провайдер рыночных данных не ответил вовремя. Попробуйте ещё раз.",
      await readBackendDetail(response)
    );
  }

  if (response.status === 503) {
    throw new InstrumentApiError(
      "unavailable",
      "Рыночные данные сейчас недоступны. Попробуйте ещё раз позже.",
      await readBackendDetail(response)
    );
  }

  if (!response.ok) {
    const backendDetail = await readBackendDetail(response);
    throw new InstrumentApiError(
      "unexpected",
      "Не удалось загрузить данные инструмента. Попробуйте ещё раз.",
      backendDetail
    );
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new InstrumentApiError("unexpected", "Backend вернул некорректный ответ.");
  }

  if (!isInstrumentDetails(data)) {
    throw new InstrumentApiError("unexpected", "Backend вернул неожиданный формат данных.");
  }
  return data;
}

function isInstrumentHistoryPoint(value: unknown): value is InstrumentHistoryPoint {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return typeof candidate.timestamp === "string" && typeof candidate.close === "string";
}

function isInstrumentPriceHistory(value: unknown): value is InstrumentPriceHistory {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.ticker === "string" &&
    typeof candidate.period === "string" &&
    typeof candidate.source === "string" &&
    Array.isArray(candidate.points) &&
    candidate.points.every(isInstrumentHistoryPoint)
  );
}

/**
 * One request per call — the caller decides when to fetch (page load
 * for the default period, a period-button click for the rest). This
 * client never fetches multiple periods on its own and never retries
 * automatically (task scope §6: Twelve Data's free tier has already
 * hit real rate limits — one chart action must mean one request).
 */
export async function getInstrumentPriceHistory(
  ticker: string,
  period: InstrumentHistoryPeriod
): Promise<InstrumentPriceHistory> {
  let response: Response;
  try {
    response = await fetch(
      `${API_BASE_URL}/instruments/${encodeURIComponent(ticker)}/history?period=${encodeURIComponent(period)}`,
      {
        method: "GET",
        cache: "no-store",
      }
    );
  } catch {
    throw new InstrumentApiError(
      "network",
      "Не удалось соединиться с сервером. Проверьте, что backend запущен, и повторите попытку."
    );
  }

  if (response.status === 422) {
    throw new InstrumentApiError(
      "invalid",
      "Некорректный тикер или период графика.",
      await readBackendDetail(response)
    );
  }

  if (response.status === 404) {
    throw new InstrumentApiError(
      "not-found",
      "Инструмент не найден.",
      await readBackendDetail(response)
    );
  }

  if (response.status === 504) {
    throw new InstrumentApiError(
      "timeout",
      "Провайдер рыночных данных не ответил вовремя. Попробуйте ещё раз.",
      await readBackendDetail(response)
    );
  }

  if (response.status === 503) {
    throw new InstrumentApiError(
      "unavailable",
      "График сейчас недоступен. Попробуйте ещё раз позже.",
      await readBackendDetail(response)
    );
  }

  if (!response.ok) {
    const backendDetail = await readBackendDetail(response);
    throw new InstrumentApiError(
      "unexpected",
      "Не удалось загрузить график. Попробуйте ещё раз.",
      backendDetail
    );
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new InstrumentApiError("unexpected", "Backend вернул некорректный ответ.");
  }

  if (!isInstrumentPriceHistory(data)) {
    throw new InstrumentApiError("unexpected", "Backend вернул неожиданный формат данных.");
  }
  return data;
}

function isNewsRelevance(value: unknown): value is NewsRelevance {
  return value === "high" || value === "medium" || value === "low";
}

function isNullableNewsRelevance(value: unknown): value is NewsRelevance | null {
  return value === null || isNewsRelevance(value);
}

function isNewsRelationship(value: unknown): value is NewsRelationship {
  return (
    value === "company" ||
    value === "sector" ||
    value === "market" ||
    value === "macro" ||
    value === "indirect" ||
    value === "noise"
  );
}

function isNullableNewsRelationship(value: unknown): value is NewsRelationship | null {
  return value === null || isNewsRelationship(value);
}

function isInstrumentNewsItem(value: unknown): value is InstrumentNewsItem {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.id === "string" &&
    typeof candidate.headline === "string" &&
    typeof candidate.source === "string" &&
    typeof candidate.published_at === "string" &&
    typeof candidate.url === "string" &&
    isNullableString(candidate.summary) &&
    typeof candidate.enriched === "boolean" &&
    isNullableString(candidate.summary_ru) &&
    isNullableString(candidate.why_it_matters) &&
    isNullableNewsRelevance(candidate.relevance) &&
    isNullableNewsRelationship(candidate.relationship) &&
    isNullableString(candidate.impact_hypothesis)
  );
}

function isInstrumentNewsResponse(value: unknown): value is InstrumentNewsResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.ticker === "string" &&
    typeof candidate.source === "string" &&
    Array.isArray(candidate.items) &&
    candidate.items.every(isInstrumentNewsItem)
  );
}

/**
 * Loads exactly once per instrument-page visit (the caller — see
 * `InstrumentNewsSection.tsx` — fetches on mount and only again via an
 * explicit user "Повторить" click, never automatically). No provider
 * pagination/raw parameters are exposed here — the backend always
 * decides the window and the cap (task scope §3, §10).
 */
export async function getInstrumentNews(ticker: string): Promise<InstrumentNewsResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/instruments/${encodeURIComponent(ticker)}/news`, {
      method: "GET",
      cache: "no-store",
    });
  } catch {
    throw new InstrumentApiError(
      "network",
      "Не удалось соединиться с сервером. Проверьте, что backend запущен, и повторите попытку."
    );
  }

  if (response.status === 422) {
    throw new InstrumentApiError(
      "invalid",
      "Некорректный тикер.",
      await readBackendDetail(response)
    );
  }

  if (response.status === 504) {
    throw new InstrumentApiError(
      "timeout",
      "Провайдер новостей не ответил вовремя. Попробуйте ещё раз.",
      await readBackendDetail(response)
    );
  }

  if (response.status === 503) {
    throw new InstrumentApiError(
      "unavailable",
      "Новости сейчас недоступны.",
      await readBackendDetail(response)
    );
  }

  if (!response.ok) {
    const backendDetail = await readBackendDetail(response);
    throw new InstrumentApiError(
      "unexpected",
      "Не удалось загрузить новости. Попробуйте ещё раз.",
      backendDetail
    );
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new InstrumentApiError("unexpected", "Backend вернул некорректный ответ.");
  }

  if (!isInstrumentNewsResponse(data)) {
    throw new InstrumentApiError("unexpected", "Backend вернул неожиданный формат данных.");
  }
  return data;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isInstrumentConfidenceLevel(value: unknown): value is InstrumentConfidenceLevel {
  return value === "high" || value === "medium" || value === "low";
}

function isAnalysisHorizon(value: unknown): value is AnalysisHorizon {
  return value === "short" || value === "medium" || value === "long";
}

function isNullableAnalysisHorizon(value: unknown): value is AnalysisHorizon | null {
  return value === null || isAnalysisHorizon(value);
}

function isDirectionalView(value: unknown): value is DirectionalView {
  return (
    value === "strongly_bullish" ||
    value === "bullish" ||
    value === "neutral" ||
    value === "bearish" ||
    value === "strongly_bearish"
  );
}

function isNullableDirectionalView(value: unknown): value is DirectionalView | null {
  return value === null || isDirectionalView(value);
}

function isForecastState(value: unknown): value is ForecastState {
  return (
    value === "forecast" ||
    value === "no_quality_setup" ||
    value === "insufficient_edge" ||
    value === "insufficient_data"
  );
}

function isNullableForecastState(value: unknown): value is ForecastState | null {
  return value === null || isForecastState(value);
}

function isInstrumentKeyFact(value: unknown): value is InstrumentKeyFact {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return typeof candidate.fact === "string" && typeof candidate.source === "string";
}

function isInstrumentKeyFactArray(value: unknown): value is InstrumentKeyFact[] {
  return Array.isArray(value) && value.every(isInstrumentKeyFact);
}

function isInstrumentAiAnalysis(value: unknown): value is InstrumentAiAnalysis {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.ticker === "string" &&
    typeof candidate.generated_at === "string" &&
    typeof candidate.summary === "string" &&
    typeof candidate.price_context === "string" &&
    typeof candidate.news_context === "string" &&
    isInstrumentKeyFactArray(candidate.key_facts) &&
    typeof candidate.insight_hypothesis === "string" &&
    isInstrumentConfidenceLevel(candidate.confidence) &&
    typeof candidate.confidence_reason === "string" &&
    isStringArray(candidate.considerations) &&
    isStringArray(candidate.risks) &&
    isStringArray(candidate.key_drivers) &&
    typeof candidate.data_freshness === "string" &&
    typeof candidate.disclaimer === "string" &&
    typeof candidate.source === "string" &&
    typeof candidate.analysis_token === "string" &&
    isAnalysisHorizon(candidate.horizon) &&
    isForecastState(candidate.forecast_state) &&
    isNullableDirectionalView(candidate.directional_view) &&
    typeof candidate.concise_verdict === "string" &&
    isNullableString(candidate.base_case) &&
    isNullableString(candidate.bullish_case) &&
    isNullableString(candidate.bearish_case) &&
    isStringArray(candidate.catalysts) &&
    isStringArray(candidate.invalidation_conditions) &&
    isStringArray(candidate.what_to_watch_next) &&
    typeof candidate.check_after === "string" &&
    typeof candidate.uncertainty === "string" &&
    isStringArray(candidate.context_categories_used)
  );
}

function isInsightSummary(value: unknown): value is InsightSummary {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.id === "number" &&
    typeof candidate.ticker === "string" &&
    typeof candidate.generated_at === "string" &&
    typeof candidate.created_at === "string" &&
    isInstrumentConfidenceLevel(candidate.confidence) &&
    typeof candidate.summary === "string" &&
    isNullableAnalysisHorizon(candidate.horizon) &&
    isNullableForecastState(candidate.forecast_state) &&
    isNullableDirectionalView(candidate.directional_view) &&
    isNullableString(candidate.concise_verdict)
  );
}

function isInstrumentInsightsResponse(value: unknown): value is InstrumentInsightsResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.ticker === "string" &&
    Array.isArray(candidate.items) &&
    candidate.items.every(isInsightSummary)
  );
}

function isRecentInsightsResponse(value: unknown): value is RecentInsightsResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return Array.isArray(candidate.items) && candidate.items.every(isInsightSummary);
}

function isInsightDetail(value: unknown): value is InsightDetail {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.id === "number" &&
    typeof candidate.ticker === "string" &&
    typeof candidate.generated_at === "string" &&
    typeof candidate.created_at === "string" &&
    typeof candidate.summary === "string" &&
    typeof candidate.price_context === "string" &&
    typeof candidate.news_context === "string" &&
    isInstrumentKeyFactArray(candidate.key_facts) &&
    typeof candidate.insight_hypothesis === "string" &&
    isInstrumentConfidenceLevel(candidate.confidence) &&
    typeof candidate.confidence_reason === "string" &&
    isStringArray(candidate.considerations) &&
    isStringArray(candidate.risks) &&
    isStringArray(candidate.key_drivers) &&
    typeof candidate.data_freshness === "string" &&
    typeof candidate.disclaimer === "string" &&
    typeof candidate.provider === "string" &&
    typeof candidate.model === "string" &&
    typeof candidate.prompt_version === "string" &&
    typeof candidate.schema_version === "string" &&
    isNullableAnalysisHorizon(candidate.horizon) &&
    isNullableForecastState(candidate.forecast_state) &&
    isNullableDirectionalView(candidate.directional_view) &&
    isNullableString(candidate.concise_verdict) &&
    isNullableString(candidate.base_case) &&
    isNullableString(candidate.bullish_case) &&
    isNullableString(candidate.bearish_case) &&
    isStringArray(candidate.catalysts) &&
    isStringArray(candidate.invalidation_conditions) &&
    isStringArray(candidate.what_to_watch_next) &&
    isNullableString(candidate.check_after) &&
    isNullableString(candidate.uncertainty) &&
    isStringArray(candidate.context_categories_used)
  );
}

/**
 * POST, never automatic — the caller (`AiAnalysisSection.tsx`) only
 * calls this from an explicit "Сгенерировать AI-анализ"/"Обновить
 * AI-анализ" button click, never on page load, `F5`, chart-period
 * switch, or news load (task scope §11: cost discipline — one click
 * is at most one generation call, and this client never retries
 * automatically either).
 *
 * No prompt is ever sent — the backend accepts no request body for
 * this endpoint at all (task scope §6).
 *
 * Phase 2B (FR-006): `horizon` is a required parameter — this client
 * never supplies a default; the caller (`AiAnalysisSection.tsx`) only
 * calls this once the user has explicitly picked SHORT/MEDIUM/LONG.
 */
export async function generateInstrumentAnalysis(
  ticker: string,
  horizon: AnalysisHorizon
): Promise<InstrumentAiAnalysis> {
  let response: Response;
  try {
    response = await fetch(
      `${API_BASE_URL}/instruments/${encodeURIComponent(ticker)}/analysis?horizon=${encodeURIComponent(horizon)}`,
      {
        method: "POST",
        cache: "no-store",
      }
    );
  } catch {
    throw new InstrumentApiError(
      "network",
      "Не удалось соединиться с сервером. Проверьте, что backend запущен, и повторите попытку."
    );
  }

  if (response.status === 422) {
    throw new InstrumentApiError(
      "invalid",
      "Некорректный тикер или горизонт анализа.",
      await readBackendDetail(response)
    );
  }

  if (response.status === 504) {
    throw new InstrumentApiError(
      "timeout",
      "AI-провайдер не ответил вовремя. Попробуйте ещё раз.",
      await readBackendDetail(response)
    );
  }

  if (response.status === 503) {
    throw new InstrumentApiError(
      "unavailable",
      "AI-анализ сейчас недоступен. Попробуйте ещё раз позже.",
      await readBackendDetail(response)
    );
  }

  if (!response.ok) {
    const backendDetail = await readBackendDetail(response);
    throw new InstrumentApiError(
      "unexpected",
      "Не удалось сгенерировать AI-анализ. Попробуйте ещё раз.",
      backendDetail
    );
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new InstrumentApiError("unexpected", "Backend вернул некорректный ответ.");
  }

  if (!isInstrumentAiAnalysis(data)) {
    throw new InstrumentApiError("unexpected", "Backend вернул неожиданный формат данных.");
  }
  return data;
}

function isInsightRating(value: unknown): value is InsightRating {
  return value === "useful" || value === "partially_useful" || value === "not_useful";
}

function isNullableInsightRating(value: unknown): value is InsightRating | null {
  return value === null || isInsightRating(value);
}

function isInsightEvaluation(value: unknown): value is InsightEvaluation {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.insight_id === "number" &&
    isNullableInsightRating(candidate.rating) &&
    isNullableString(candidate.rated_at) &&
    isNullableString(candidate.outcome_note) &&
    isNullableString(candidate.outcome_recorded_at) &&
    typeof candidate.created_at === "string" &&
    isNullableString(candidate.updated_at)
  );
}

function isInstrumentSearchResult(value: unknown): value is InstrumentSearchResult {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.ticker === "string" &&
    typeof candidate.name === "string" &&
    isNullableString(candidate.exchange) &&
    isNullableString(candidate.instrument_type) &&
    isNullableString(candidate.currency)
  );
}

function isInstrumentSearchResponse(value: unknown): value is InstrumentSearchResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.query === "string" &&
    Array.isArray(candidate.items) &&
    candidate.items.every(isInstrumentSearchResult)
  );
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

/**
 * The caller (`WatchlistPanel.tsx`) is responsible for debouncing and
 * for passing an `AbortSignal` so a superseded in-flight search never
 * overwrites a newer one with a stale response — this function itself
 * fires exactly one request per call, no retry. A caller-triggered
 * abort rejects with the DOM `AbortError` (rethrown as-is, not wrapped
 * in `InstrumentApiError`) so the caller can distinguish "cancelled by
 * a newer query" from a real failure and silently ignore it.
 */
export async function searchInstruments(
  query: string,
  signal?: AbortSignal
): Promise<InstrumentSearchResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/instruments/search?q=${encodeURIComponent(query)}`, {
      method: "GET",
      cache: "no-store",
      signal,
    });
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }
    throw new InstrumentApiError(
      "network",
      "Не удалось соединиться с сервером. Проверьте, что backend запущен, и повторите попытку."
    );
  }

  if (response.status === 422) {
    throw new InstrumentApiError(
      "invalid",
      "Слишком короткий запрос.",
      await readBackendDetail(response)
    );
  }

  if (response.status === 504) {
    throw new InstrumentApiError(
      "timeout",
      "Провайдер поиска не ответил вовремя. Попробуйте ещё раз.",
      await readBackendDetail(response)
    );
  }

  if (response.status === 503) {
    throw new InstrumentApiError(
      "unavailable",
      "Поиск сейчас недоступен.",
      await readBackendDetail(response)
    );
  }

  if (!response.ok) {
    const backendDetail = await readBackendDetail(response);
    throw new InstrumentApiError(
      "unexpected",
      "Не удалось выполнить поиск. Попробуйте ещё раз.",
      backendDetail
    );
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new InstrumentApiError("unexpected", "Backend вернул некорректный ответ.");
  }

  if (!isInstrumentSearchResponse(data)) {
    throw new InstrumentApiError("unexpected", "Backend вернул неожиданный формат данных.");
  }
  return data;
}

/**
 * Persists the analysis identified by `analysisToken` (from a prior
 * `generateInstrumentAnalysis` call) — never sends analysis content
 * itself. Only ever called from an explicit "Сохранить инсайт" click
 * (Product Owner decision: explicit save, not auto-save).
 */
export async function saveInsight(ticker: string, analysisToken: string): Promise<InsightDetail> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/instruments/${encodeURIComponent(ticker)}/insights`, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ analysis_token: analysisToken }),
    });
  } catch {
    throw new InstrumentApiError(
      "network",
      "Не удалось соединиться с сервером. Проверьте, что backend запущен, и повторите попытку."
    );
  }

  if (response.status === 422) {
    throw new InstrumentApiError(
      "invalid",
      "Некорректный тикер.",
      await readBackendDetail(response)
    );
  }

  if (response.status === 404) {
    throw new InstrumentApiError(
      "not-found",
      "Не удалось сохранить: этот AI-анализ уже неактуален (истёк или уже сохранён). Сгенерируйте анализ заново.",
      await readBackendDetail(response)
    );
  }

  if (response.status === 503) {
    throw new InstrumentApiError(
      "unavailable",
      "Сохранение сейчас недоступно. Попробуйте ещё раз позже.",
      await readBackendDetail(response)
    );
  }

  if (!response.ok) {
    const backendDetail = await readBackendDetail(response);
    throw new InstrumentApiError(
      "unexpected",
      "Не удалось сохранить инсайт. Попробуйте ещё раз.",
      backendDetail
    );
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new InstrumentApiError("unexpected", "Backend вернул некорректный ответ.");
  }

  if (!isInsightDetail(data)) {
    throw new InstrumentApiError("unexpected", "Backend вернул неожиданный формат данных.");
  }
  return data;
}

/**
 * Newest-first, bounded history (task scope §14) — loads on mount (see
 * `InsightHistorySection.tsx`) and again only via an explicit
 * "Повторить"/reload action, never polled.
 */
export async function getInstrumentInsights(ticker: string): Promise<InstrumentInsightsResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/instruments/${encodeURIComponent(ticker)}/insights`, {
      method: "GET",
      cache: "no-store",
    });
  } catch {
    throw new InstrumentApiError(
      "network",
      "Не удалось соединиться с сервером. Проверьте, что backend запущен, и повторите попытку."
    );
  }

  if (response.status === 422) {
    throw new InstrumentApiError(
      "invalid",
      "Некорректный тикер.",
      await readBackendDetail(response)
    );
  }

  if (response.status === 503) {
    throw new InstrumentApiError(
      "unavailable",
      "История AI-анализов сейчас недоступна.",
      await readBackendDetail(response)
    );
  }

  if (!response.ok) {
    const backendDetail = await readBackendDetail(response);
    throw new InstrumentApiError(
      "unexpected",
      "Не удалось загрузить историю AI-анализов. Попробуйте ещё раз.",
      backendDetail
    );
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new InstrumentApiError("unexpected", "Backend вернул некорректный ответ.");
  }

  if (!isInstrumentInsightsResponse(data)) {
    throw new InstrumentApiError("unexpected", "Backend вернул неожиданный формат данных.");
  }
  return data;
}

/**
 * Cross-ticker equivalent of `getInstrumentInsights` (Phase 1,
 * Insights/History area — `GET /insights?limit=N`). Newest-first,
 * bounded, read-only. Used by both `/insights` and the Overview page's
 * "recent insights" widget.
 */
export async function getRecentInsights(limit?: number): Promise<RecentInsightsResponse> {
  const query = limit !== undefined ? `?limit=${encodeURIComponent(String(limit))}` : "";
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/insights${query}`, {
      method: "GET",
      cache: "no-store",
    });
  } catch {
    throw new InstrumentApiError(
      "network",
      "Не удалось соединиться с сервером. Проверьте, что backend запущен, и повторите попытку."
    );
  }

  if (response.status === 422) {
    throw new InstrumentApiError(
      "invalid",
      "Некорректный лимит.",
      await readBackendDetail(response)
    );
  }

  if (response.status === 503) {
    throw new InstrumentApiError(
      "unavailable",
      "История инсайтов сейчас недоступна.",
      await readBackendDetail(response)
    );
  }

  if (!response.ok) {
    const backendDetail = await readBackendDetail(response);
    throw new InstrumentApiError(
      "unexpected",
      "Не удалось загрузить историю инсайтов. Попробуйте ещё раз.",
      backendDetail
    );
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new InstrumentApiError("unexpected", "Backend вернул некорректный ответ.");
  }

  if (!isRecentInsightsResponse(data)) {
    throw new InstrumentApiError("unexpected", "Backend вернул неожиданный формат данных.");
  }
  return data;
}

/**
 * Sets (or replaces — UJ-014 explicitly allows changing a previous
 * rating) the user's evaluation of a saved insight. `PUT`, not `POST`:
 * calling this twice with a different value simply replaces it, never
 * creates a duplicate.
 */
export async function evaluateInsight(
  insightId: number,
  rating: InsightRating
): Promise<InsightEvaluation> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/insights/${encodeURIComponent(String(insightId))}/evaluation`, {
      method: "PUT",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rating }),
    });
  } catch {
    throw new InstrumentApiError(
      "network",
      "Не удалось соединиться с сервером. Проверьте, что backend запущен, и повторите попытку."
    );
  }

  if (response.status === 422) {
    throw new InstrumentApiError("invalid", "Некорректная оценка.", await readBackendDetail(response));
  }

  if (response.status === 404) {
    throw new InstrumentApiError("not-found", "Инсайт не найден.", await readBackendDetail(response));
  }

  if (response.status === 503) {
    throw new InstrumentApiError(
      "unavailable",
      "Оценка сейчас недоступна. Попробуйте ещё раз позже.",
      await readBackendDetail(response)
    );
  }

  if (!response.ok) {
    const backendDetail = await readBackendDetail(response);
    throw new InstrumentApiError(
      "unexpected",
      "Не удалось сохранить оценку. Попробуйте ещё раз.",
      backendDetail
    );
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new InstrumentApiError("unexpected", "Backend вернул некорректный ответ.");
  }

  if (!isInsightEvaluation(data)) {
    throw new InstrumentApiError("unexpected", "Backend вернул неожиданный формат данных.");
  }
  return data;
}

/**
 * Fetches the evaluation/outcome record for an insight, if any. `404`
 * ("not-found") covers both "insight doesn't exist" and "insight exists
 * but was never evaluated" — the caller (`InsightHistorySection.tsx`)
 * treats both as "not yet evaluated" for display purposes.
 */
export async function getInsightEvaluation(insightId: number): Promise<InsightEvaluation> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/insights/${encodeURIComponent(String(insightId))}/evaluation`, {
      method: "GET",
      cache: "no-store",
    });
  } catch {
    throw new InstrumentApiError(
      "network",
      "Не удалось соединиться с сервером. Проверьте, что backend запущен, и повторите попытку."
    );
  }

  if (response.status === 404) {
    throw new InstrumentApiError("not-found", "Оценка не найдена.", await readBackendDetail(response));
  }

  if (response.status === 503) {
    throw new InstrumentApiError(
      "unavailable",
      "Оценка сейчас недоступна.",
      await readBackendDetail(response)
    );
  }

  if (!response.ok) {
    const backendDetail = await readBackendDetail(response);
    throw new InstrumentApiError(
      "unexpected",
      "Не удалось загрузить оценку. Попробуйте ещё раз.",
      backendDetail
    );
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new InstrumentApiError("unexpected", "Backend вернул некорректный ответ.");
  }

  if (!isInsightEvaluation(data)) {
    throw new InstrumentApiError("unexpected", "Backend вернул неожиданный формат данных.");
  }
  return data;
}

/**
 * Records (or replaces) the manual outcome note for a saved insight
 * (FR-036/FR-038) — independent of whether a rating exists yet. Not a
 * Trade Journal: only a short free-text description, never entry/exit
 * price, quantity, side, or P&L (task scope §18).
 */
export async function recordInsightOutcome(
  insightId: number,
  outcomeNote: string
): Promise<InsightEvaluation> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/insights/${encodeURIComponent(String(insightId))}/outcome`, {
      method: "PUT",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ outcome_note: outcomeNote }),
    });
  } catch {
    throw new InstrumentApiError(
      "network",
      "Не удалось соединиться с сервером. Проверьте, что backend запущен, и повторите попытку."
    );
  }

  if (response.status === 422) {
    throw new InstrumentApiError(
      "invalid",
      "Некорректный результат — заполните поле.",
      await readBackendDetail(response)
    );
  }

  if (response.status === 404) {
    throw new InstrumentApiError("not-found", "Инсайт не найден.", await readBackendDetail(response));
  }

  if (response.status === 503) {
    throw new InstrumentApiError(
      "unavailable",
      "Фиксация результата сейчас недоступна. Попробуйте ещё раз позже.",
      await readBackendDetail(response)
    );
  }

  if (!response.ok) {
    const backendDetail = await readBackendDetail(response);
    throw new InstrumentApiError(
      "unexpected",
      "Не удалось зафиксировать результат. Попробуйте ещё раз.",
      backendDetail
    );
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new InstrumentApiError("unexpected", "Backend вернул некорректный ответ.");
  }

  if (!isInsightEvaluation(data)) {
    throw new InstrumentApiError("unexpected", "Backend вернул неожиданный формат данных.");
  }
  return data;
}

/**
 * Fetches one full persisted insight on demand — called only when the
 * user expands a history item (task scope §14: list stays compact,
 * detail is lazy).
 */
export async function getInsightDetail(insightId: number): Promise<InsightDetail> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/insights/${encodeURIComponent(String(insightId))}`, {
      method: "GET",
      cache: "no-store",
    });
  } catch {
    throw new InstrumentApiError(
      "network",
      "Не удалось соединиться с сервером. Проверьте, что backend запущен, и повторите попытку."
    );
  }

  if (response.status === 404) {
    throw new InstrumentApiError(
      "not-found",
      "Инсайт не найден.",
      await readBackendDetail(response)
    );
  }

  if (response.status === 503) {
    throw new InstrumentApiError(
      "unavailable",
      "Инсайт сейчас недоступен.",
      await readBackendDetail(response)
    );
  }

  if (!response.ok) {
    const backendDetail = await readBackendDetail(response);
    throw new InstrumentApiError(
      "unexpected",
      "Не удалось загрузить инсайт. Попробуйте ещё раз.",
      backendDetail
    );
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new InstrumentApiError("unexpected", "Backend вернул некорректный ответ.");
  }

  if (!isInsightDetail(data)) {
    throw new InstrumentApiError("unexpected", "Backend вернул неожиданный формат данных.");
  }
  return data;
}
