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

export interface InstrumentNewsItem {
  id: string;
  headline: string;
  source: string;
  published_at: string;
  url: string;
  /** `null`, never an invented placeholder, when the provider didn't return one. */
  summary: string | null;
}

export interface InstrumentNewsResponse {
  ticker: string;
  source: string;
  /** Always newest-first, always capped at a fixed size — never provider-controlled pagination. */
  items: InstrumentNewsItem[];
}

export interface InstrumentAiAnalysis {
  ticker: string;
  generated_at: string;
  summary: string;
  price_context: string;
  news_context: string;
  risks: string[];
  disclaimer: string;
  source: string;
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
    isNullableString(candidate.summary)
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
    Array.isArray(candidate.risks) &&
    candidate.risks.every((risk) => typeof risk === "string") &&
    typeof candidate.disclaimer === "string" &&
    typeof candidate.source === "string"
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
 */
export async function generateInstrumentAnalysis(ticker: string): Promise<InstrumentAiAnalysis> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/instruments/${encodeURIComponent(ticker)}/analysis`, {
      method: "POST",
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
