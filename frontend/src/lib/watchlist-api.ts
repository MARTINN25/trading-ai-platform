/**
 * Typed client for the existing FastAPI watchlist endpoints
 * (`GET /watchlist`, `POST /watchlist` — see
 * `backend/src/trading_ai/api/routes/watchlist.py`). No generic HTTP
 * client abstraction — just the two functions this UI needs, built on
 * the built-in `fetch` (ADR-0003, §22.2: frontend uses the documented
 * HTTP contract; no axios/React Query/SWR).
 *
 * Backend error `detail` strings are English/technical
 * (`trading_ai/watchlist/domain.py`) and are read defensively here,
 * but never shown to the user as-is — user-facing messages are fixed,
 * Russian, and chosen from the HTTP status/failure kind (ADR-0003,
 * §24, §27: user-facing messages are fully Russian, technical detail
 * is not shown).
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

export type WatchlistApiErrorKind = "duplicate" | "invalid" | "network" | "unexpected";

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
