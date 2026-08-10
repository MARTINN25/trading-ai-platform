/**
 * Typed client for the existing FastAPI watchlist endpoints
 * (`GET /watchlist`, `POST /watchlist`, `DELETE /watchlist/{id}`,
 * `GET /watchlist/quotes` — see
 * `backend/src/trading_ai/api/routes/watchlist.py`). No generic HTTP
 * client abstraction — just the functions this UI needs, built on the
 * built-in `fetch` (ADR-0003, §22.2: frontend uses the documented HTTP
 * contract; no axios/React Query/SWR).
 *
 * Backend error `detail` strings are English/technical
 * (`trading_ai/watchlist/domain.py`) and are read defensively here,
 * but never shown to the user as-is — user-facing messages are fixed,
 * Russian, and chosen from the HTTP status/failure kind (ADR-0003,
 * §24, §27: user-facing messages are fully Russian, technical detail
 * is not shown).
 *
 * Market data (`getWatchlistQuotes`) is read-only display data from
 * the backend's market-data gateway — the browser never talks to the
 * market-data provider or sees its API key (ADR-0003 §17: frontend
 * never holds provider credentials).
 */

const DEFAULT_DEV_API_BASE_URL = "http://127.0.0.1:8000";

// Single, centralized place for the base URL and its development
// fallback (ADR-0003, §25: NEXT_PUBLIC_ variables are public by
// definition, not secrets). Never read directly by components.
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_DEV_API_BASE_URL;

export interface WatchlistItem {
  id: number;
  ticker: string;
  created_at: string;
}

export interface CreateWatchlistItemRequest {
  ticker: string;
}

/**
 * A watchlist row plus its best-effort quote. Numeric fields arrive as
 * JSON strings (backend `Decimal` — exact financial precision, not a
 * float) and are parsed with `Number()` only for display, never for
 * further arithmetic here (ADR-0003 §17: frontend does not do
 * business/financial computation, only presentation).
 *
 * Exactly one of `quote_error` / the price fields is set — never
 * both, never neither. `quote_error` is a fixed safe category
 * (`"timeout" | "rate_limited" | "unsupported" | "unavailable"`), not
 * provider wording.
 */
export interface WatchlistItemQuote {
  id: number;
  ticker: string;
  created_at: string;
  price: string | null;
  change: string | null;
  change_percent: string | null;
  as_of: string | null;
  source: string | null;
  quote_error: string | null;
}

export type WatchlistApiErrorKind =
  | "duplicate"
  | "invalid"
  | "not-found"
  | "network"
  | "unexpected";

/** Thrown by every function in this module — always has a Russian, user-safe `message`. */
export class WatchlistApiError extends Error {
  readonly kind: WatchlistApiErrorKind;
  /** Raw backend `detail`, if any — for developer diagnostics only, never rendered. */
  readonly backendDetail?: string;

  constructor(kind: WatchlistApiErrorKind, message: string, backendDetail?: string) {
    super(message);
    this.name = "WatchlistApiError";
    this.kind = kind;
    this.backendDetail = backendDetail;
  }
}

function isWatchlistItem(value: unknown): value is WatchlistItem {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.id === "number" &&
    typeof candidate.ticker === "string" &&
    typeof candidate.created_at === "string"
  );
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isWatchlistItemQuote(value: unknown): value is WatchlistItemQuote {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.id === "number" &&
    typeof candidate.ticker === "string" &&
    typeof candidate.created_at === "string" &&
    isNullableString(candidate.price) &&
    isNullableString(candidate.change) &&
    isNullableString(candidate.change_percent) &&
    isNullableString(candidate.as_of) &&
    isNullableString(candidate.source) &&
    isNullableString(candidate.quote_error)
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

async function doFetch(path: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw new WatchlistApiError(
      "network",
      "Не удалось соединиться с сервером. Проверьте, что backend запущен, и повторите попытку."
    );
  }
}

export async function getWatchlist(): Promise<WatchlistItem[]> {
  const response = await doFetch("/watchlist", {
    method: "GET",
    // Never cache: the user must always see the current list, not a
    // stale one (this option is standard Fetch API, honored by the
    // browser regardless of origin).
    cache: "no-store",
  });

  if (!response.ok) {
    const backendDetail = await readBackendDetail(response);
    throw new WatchlistApiError(
      "unexpected",
      "Не удалось загрузить watchlist. Попробуйте ещё раз.",
      backendDetail
    );
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new WatchlistApiError("unexpected", "Backend вернул некорректный ответ.");
  }

  if (!Array.isArray(data) || !data.every(isWatchlistItem)) {
    throw new WatchlistApiError("unexpected", "Backend вернул неожиданный формат данных.");
  }
  return data;
}

export async function addWatchlistItem(ticker: string): Promise<WatchlistItem> {
  const response = await doFetch("/watchlist", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticker } satisfies CreateWatchlistItemRequest),
    cache: "no-store",
  });

  if (response.status === 409) {
    const backendDetail = await readBackendDetail(response);
    throw new WatchlistApiError(
      "duplicate",
      "Такой тикер уже есть в списке.",
      backendDetail
    );
  }

  if (response.status === 422) {
    const backendDetail = await readBackendDetail(response);
    throw new WatchlistApiError(
      "invalid",
      "Некорректный тикер: буквы, цифры, «.» или «-», не более 15 символов.",
      backendDetail
    );
  }

  if (!response.ok) {
    const backendDetail = await readBackendDetail(response);
    throw new WatchlistApiError(
      "unexpected",
      "Не удалось добавить тикер. Попробуйте ещё раз.",
      backendDetail
    );
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new WatchlistApiError("unexpected", "Backend вернул некорректный ответ.");
  }

  if (!isWatchlistItem(data)) {
    throw new WatchlistApiError("unexpected", "Backend вернул неожиданный формат данных.");
  }
  return data;
}

export async function removeWatchlistItem(id: number): Promise<void> {
  const response = await doFetch(`/watchlist/${id}`, {
    method: "DELETE",
    cache: "no-store",
  });

  // 204 No Content — success, no body to read.
  if (response.status === 204) {
    return;
  }

  if (response.status === 404) {
    const backendDetail = await readBackendDetail(response);
    throw new WatchlistApiError(
      "not-found",
      "Запись уже удалена или не найдена.",
      backendDetail
    );
  }

  const backendDetail = await readBackendDetail(response);
  throw new WatchlistApiError(
    "unexpected",
    "Не удалось удалить тикер. Попробуйте ещё раз.",
    backendDetail
  );
}

export async function getWatchlistQuotes(): Promise<WatchlistItemQuote[]> {
  const response = await doFetch("/watchlist/quotes", {
    method: "GET",
    // Same reasoning as getWatchlist(): always the current data, never
    // a stale cached quote silently shown as fresh.
    cache: "no-store",
  });

  if (response.status === 503) {
    throw new WatchlistApiError(
      "unexpected",
      "Рыночные данные сейчас недоступны на backend.",
      await readBackendDetail(response)
    );
  }

  if (!response.ok) {
    const backendDetail = await readBackendDetail(response);
    throw new WatchlistApiError(
      "unexpected",
      "Не удалось загрузить рыночные данные. Попробуйте ещё раз.",
      backendDetail
    );
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new WatchlistApiError("unexpected", "Backend вернул некорректный ответ.");
  }

  if (!Array.isArray(data) || !data.every(isWatchlistItemQuote)) {
    throw new WatchlistApiError("unexpected", "Backend вернул неожиданный формат данных.");
  }
  return data;
}
