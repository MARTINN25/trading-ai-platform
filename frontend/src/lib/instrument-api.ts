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
