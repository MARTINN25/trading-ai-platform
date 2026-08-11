/**
 * Typed client for the trade journal endpoints
 * (`POST /journal`, `GET /journal`, `GET /journal/{id}`,
 * `PUT /journal/{id}` — see `backend/src/trading_ai/api/routes/journal.py`).
 * No generic HTTP client abstraction — same `doFetch` pattern as
 * `watchlist-api.ts` (ADR-0003, §22.2).
 *
 * FR-030: a manual, single-user trade journal — never broker/order/
 * portfolio functionality. This client sends only journal-owned fields
 * (ticker, direction, result status/note, optional insight link) —
 * never insight content or provenance (backend task scope §6).
 */

const DEFAULT_DEV_API_BASE_URL = "http://127.0.0.1:8000";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_DEV_API_BASE_URL;

/** Product Owner decision: categorical enum, not free text. */
export type TradeDirection = "long" | "short";

/** Product Owner decision: categorical status + optional free text —
 * never a numeric P&L field, which FR-030 does not require. */
export type TradeResultStatus = "profit" | "loss" | "breakeven" | "open";

export interface JournalEntry {
  id: number;
  ticker: string;
  direction: TradeDirection;
  result_status: TradeResultStatus;
  result_note: string | null;
  insight_id: number | null;
  created_at: string;
  updated_at: string | null;
}

export interface JournalEntryInput {
  ticker: string;
  direction: TradeDirection;
  result_status: TradeResultStatus;
  result_note: string | null;
  insight_id: number | null;
}

export type JournalApiErrorKind = "invalid" | "not-found" | "unavailable" | "network" | "unexpected";

/** Thrown by every function in this module — always has a Russian, user-safe `message`. */
export class JournalApiError extends Error {
  readonly kind: JournalApiErrorKind;
  /** Raw backend `detail`, if any — for developer diagnostics only, never rendered. */
  readonly backendDetail?: string;

  constructor(kind: JournalApiErrorKind, message: string, backendDetail?: string) {
    super(message);
    this.name = "JournalApiError";
    this.kind = kind;
    this.backendDetail = backendDetail;
  }
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isTradeDirection(value: unknown): value is TradeDirection {
  return value === "long" || value === "short";
}

function isTradeResultStatus(value: unknown): value is TradeResultStatus {
  return value === "profit" || value === "loss" || value === "breakeven" || value === "open";
}

function isJournalEntry(value: unknown): value is JournalEntry {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.id === "number" &&
    typeof candidate.ticker === "string" &&
    isTradeDirection(candidate.direction) &&
    isTradeResultStatus(candidate.result_status) &&
    isNullableString(candidate.result_note) &&
    (candidate.insight_id === null || typeof candidate.insight_id === "number") &&
    typeof candidate.created_at === "string" &&
    isNullableString(candidate.updated_at)
  );
}

function isJournalEntriesResponse(value: unknown): value is { items: JournalEntry[] } {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return Array.isArray(candidate.items) && candidate.items.every(isJournalEntry);
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
    // Not JSON — no detail available, and that raw body is never shown to the user either way.
  }
  return undefined;
}

async function doFetch(path: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw new JournalApiError(
      "network",
      "Не удалось соединиться с сервером. Проверьте, что backend запущен, и повторите попытку."
    );
  }
}

async function parseJournalEntry(response: Response): Promise<JournalEntry> {
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new JournalApiError("unexpected", "Backend вернул некорректный ответ.");
  }
  if (!isJournalEntry(data)) {
    throw new JournalApiError("unexpected", "Backend вернул неожиданный формат данных.");
  }
  return data;
}

export async function createJournalEntry(input: JournalEntryInput): Promise<JournalEntry> {
  const response = await doFetch("/journal", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
    cache: "no-store",
  });

  if (response.status === 422) {
    throw new JournalApiError(
      "invalid",
      "Некорректные данные записи. Проверьте тикер и заполненные поля.",
      await readBackendDetail(response)
    );
  }

  if (response.status === 404) {
    throw new JournalApiError(
      "not-found",
      "Связанный инсайт не найден — возможно, он был удалён или ссылка устарела.",
      await readBackendDetail(response)
    );
  }

  if (response.status === 503) {
    throw new JournalApiError(
      "unavailable",
      "Дневник сейчас недоступен. Попробуйте ещё раз позже.",
      await readBackendDetail(response)
    );
  }

  if (!response.ok) {
    const backendDetail = await readBackendDetail(response);
    throw new JournalApiError(
      "unexpected",
      "Не удалось создать запись. Попробуйте ещё раз.",
      backendDetail
    );
  }

  return parseJournalEntry(response);
}

export async function getJournalEntries(): Promise<JournalEntry[]> {
  const response = await doFetch("/journal", {
    method: "GET",
    cache: "no-store",
  });

  if (response.status === 503) {
    throw new JournalApiError(
      "unavailable",
      "Дневник сейчас недоступен.",
      await readBackendDetail(response)
    );
  }

  if (!response.ok) {
    const backendDetail = await readBackendDetail(response);
    throw new JournalApiError(
      "unexpected",
      "Не удалось загрузить дневник. Попробуйте ещё раз.",
      backendDetail
    );
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new JournalApiError("unexpected", "Backend вернул некорректный ответ.");
  }
  if (!isJournalEntriesResponse(data)) {
    throw new JournalApiError("unexpected", "Backend вернул неожиданный формат данных.");
  }
  return data.items;
}

export async function getJournalEntry(id: number): Promise<JournalEntry> {
  const response = await doFetch(`/journal/${encodeURIComponent(String(id))}`, {
    method: "GET",
    cache: "no-store",
  });

  if (response.status === 404) {
    throw new JournalApiError("not-found", "Запись не найдена.", await readBackendDetail(response));
  }

  if (response.status === 503) {
    throw new JournalApiError(
      "unavailable",
      "Запись сейчас недоступна.",
      await readBackendDetail(response)
    );
  }

  if (!response.ok) {
    const backendDetail = await readBackendDetail(response);
    throw new JournalApiError(
      "unexpected",
      "Не удалось загрузить запись. Попробуйте ещё раз.",
      backendDetail
    );
  }

  return parseJournalEntry(response);
}

/**
 * Full-replace edit (Product Owner: editable, no delete) — every
 * journal-owned field must be resupplied, matching the backend's PUT
 * semantics.
 */
export async function updateJournalEntry(id: number, input: JournalEntryInput): Promise<JournalEntry> {
  const response = await doFetch(`/journal/${encodeURIComponent(String(id))}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
    cache: "no-store",
  });

  if (response.status === 422) {
    throw new JournalApiError(
      "invalid",
      "Некорректные данные записи. Проверьте тикер и заполненные поля.",
      await readBackendDetail(response)
    );
  }

  if (response.status === 404) {
    throw new JournalApiError(
      "not-found",
      "Запись или связанный инсайт не найдены.",
      await readBackendDetail(response)
    );
  }

  if (response.status === 503) {
    throw new JournalApiError(
      "unavailable",
      "Дневник сейчас недоступен. Попробуйте ещё раз позже.",
      await readBackendDetail(response)
    );
  }

  if (!response.ok) {
    const backendDetail = await readBackendDetail(response);
    throw new JournalApiError(
      "unexpected",
      "Не удалось обновить запись. Попробуйте ещё раз.",
      backendDetail
    );
  }

  return parseJournalEntry(response);
}
