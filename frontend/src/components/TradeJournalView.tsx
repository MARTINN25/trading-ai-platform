"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  createJournalEntry,
  getJournalEntries,
  updateJournalEntry,
  JournalApiError,
  type JournalEntry,
  type TradeDirection,
  type TradeResultStatus,
} from "@/lib/journal-api";

type ListState =
  | { status: "loading" }
  | { status: "loaded"; items: JournalEntry[] }
  | { status: "error"; message: string };

const timestampFormatter = new Intl.DateTimeFormat("ru-RU", {
  dateStyle: "medium",
  timeStyle: "short",
});

function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return timestampFormatter.format(date);
}

// Explicit plain-language explanation next to each direction value —
// a first-time user should not need prior trading knowledge to
// understand what "Лонг"/"Шорт" mean (Phase 1 UX clarification pass).
const DIRECTION_LABELS: Record<TradeDirection, string> = {
  long: "Лонг — ожидание роста",
  short: "Шорт — ожидание падения",
};

const RESULT_STATUS_LABELS: Record<TradeResultStatus, string> = {
  profit: "Прибыльная",
  loss: "Убыточная",
  breakeven: "Безубыточная",
  open: "В процессе",
};

const DIRECTION_ORDER: TradeDirection[] = ["long", "short"];
const RESULT_STATUS_ORDER: TradeResultStatus[] = ["open", "profit", "loss", "breakeven"];

interface FormValues {
  ticker: string;
  direction: TradeDirection;
  resultStatus: TradeResultStatus;
  resultNote: string;
  insightId: number | null;
}

function emptyForm(prefillTicker?: string, prefillInsightId?: number): FormValues {
  return {
    ticker: prefillTicker ?? "",
    direction: "long",
    resultStatus: "open",
    resultNote: "",
    insightId: prefillInsightId ?? null,
  };
}

function entryToForm(entry: JournalEntry): FormValues {
  return {
    ticker: entry.ticker,
    direction: entry.direction,
    resultStatus: entry.result_status,
    resultNote: entry.result_note ?? "",
    insightId: entry.insight_id,
  };
}

export default function TradeJournalView({
  prefillTicker,
  prefillInsightId,
}: {
  prefillTicker?: string;
  prefillInsightId?: number;
}) {
  const router = useRouter();
  const [state, setState] = useState<ListState>({ status: "loading" });
  // Auto-open the create form when arriving from "Добавить в дневник"
  // (task scope §14) — the user came here specifically to log a trade.
  const [showCreateForm, setShowCreateForm] = useState(
    Boolean(prefillTicker || prefillInsightId !== undefined)
  );
  const [editingId, setEditingId] = useState<number | null>(null);

  // Once the prefilled create form is closed (submitted or cancelled),
  // strip `?ticker=&insight_id=` from the URL — otherwise an F5 reload
  // would re-open the create form every time, since the prefill props
  // come straight from the still-present query string.
  function closeCreateForm(): void {
    setShowCreateForm(false);
    if (prefillTicker || prefillInsightId !== undefined) {
      router.replace("/journal");
    }
  }

  const load = useCallback(() => {
    setState({ status: "loading" });
    getJournalEntries()
      .then((items) => setState({ status: "loaded", items }))
      .catch((error: unknown) => {
        const message = error instanceof JournalApiError ? error.message : "Дневник недоступен.";
        setState({ status: "error", message });
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <main className="journal-view">
      <Link href="/" className="journal-back-link">
        ← Обзор
      </Link>

      <h1>Дневник сделок</h1>
      <p className="journal-disclaimer">
        Личный дневник для ручной фиксации сделок и их результатов — не брокерская интеграция, не
        учёт позиций и не расчёт прибыли/убытка.
      </p>
      <p className="journal-disclaimer journal-disclaimer-strong">
        Записи создаёте только вы. AI никогда не открывает сделки и не создаёт записи дневника
        самостоятельно — связанный AI-инсайт ниже показан только как контекст/основание для вашего
        решения, а не как команда или рекомендация.
      </p>

      {!showCreateForm && (
        <button type="button" onClick={() => setShowCreateForm(true)}>
          Новая запись
        </button>
      )}

      {showCreateForm && (
        <JournalEntryForm
          key="create"
          initial={emptyForm(prefillTicker, prefillInsightId)}
          submitLabel="Сохранить запись"
          onCancel={closeCreateForm}
          onSubmit={(values) =>
            createJournalEntry({
              ticker: values.ticker,
              direction: values.direction,
              result_status: values.resultStatus,
              result_note: values.resultNote.trim() === "" ? null : values.resultNote,
              insight_id: values.insightId,
            })
          }
          onSuccess={(entry) => {
            closeCreateForm();
            setState((prev) =>
              prev.status === "loaded" ? { status: "loaded", items: [entry, ...prev.items] } : prev
            );
          }}
        />
      )}

      <div aria-live="polite">
        {state.status === "loading" && <p className="journal-loading">Загрузка дневника…</p>}

        {state.status === "error" && (
          <div className="journal-error" role="alert">
            <p>{state.message}</p>
            <button type="button" onClick={load}>
              Повторить
            </button>
          </div>
        )}

        {state.status === "loaded" && state.items.length === 0 && (
          <p className="journal-empty">Записей пока нет. Нажмите «Новая запись», чтобы добавить первую.</p>
        )}

        {state.status === "loaded" && state.items.length > 0 && (
          <ul className="journal-list">
            {state.items.map((entry) => (
              <li key={entry.id} className="journal-item">
                {editingId === entry.id ? (
                  <JournalEntryForm
                    key={`edit-${entry.id}`}
                    initial={entryToForm(entry)}
                    submitLabel="Сохранить изменения"
                    onCancel={() => setEditingId(null)}
                    onSubmit={(values) =>
                      updateJournalEntry(entry.id, {
                        ticker: values.ticker,
                        direction: values.direction,
                        result_status: values.resultStatus,
                        result_note: values.resultNote.trim() === "" ? null : values.resultNote,
                        insight_id: values.insightId,
                      })
                    }
                    onSuccess={(updated) => {
                      setEditingId(null);
                      setState((prev) =>
                        prev.status === "loaded"
                          ? {
                              status: "loaded",
                              items: prev.items.map((item) => (item.id === updated.id ? updated : item)),
                            }
                          : prev
                      );
                    }}
                  />
                ) : (
                  <>
                    <div className="journal-my-trade">
                      <h3 className="journal-block-label">Моя сделка</h3>
                      <p className="journal-item-meta">
                        <Link
                          href={`/instruments/${encodeURIComponent(entry.ticker)}`}
                          className="journal-item-ticker-link"
                        >
                          {entry.ticker}
                        </Link>{" "}
                        · {formatTimestamp(entry.created_at)}
                        {entry.updated_at && <span className="journal-item-edited"> (изменено)</span>}
                      </p>
                      <p className="journal-item-fields">
                        Направление: {DIRECTION_LABELS[entry.direction]}
                        <br />
                        Результат:{" "}
                        <span className={`journal-result journal-result-${entry.result_status}`}>
                          {RESULT_STATUS_LABELS[entry.result_status]}
                        </span>
                      </p>
                      {entry.result_note && <p className="journal-item-note">{entry.result_note}</p>}
                    </div>

                    {entry.insight_id !== null && (
                      <div className="journal-linked-insight">
                        <h3 className="journal-block-label">Связанный AI-инсайт</h3>
                        <p className="journal-item-insight-link">
                          Контекст/основание, использованное при принятии решения — не команда и не
                          рекомендация AI.{" "}
                          <Link href={`/insights?open=${entry.insight_id}`}>
                            Открыть инсайт #{entry.insight_id} →
                          </Link>
                        </p>
                      </div>
                    )}

                    <button type="button" onClick={() => setEditingId(entry.id)}>
                      Изменить
                    </button>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}

function JournalEntryForm({
  initial,
  submitLabel,
  onSubmit,
  onSuccess,
  onCancel,
}: {
  initial: FormValues;
  submitLabel: string;
  onSubmit: (values: FormValues) => Promise<JournalEntry>;
  onSuccess: (entry: JournalEntry) => void;
  onCancel: () => void;
}) {
  const [values, setValues] = useState<FormValues>(initial);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(event: React.FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (values.ticker.trim() === "") {
      setError("Укажите тикер инструмента.");
      return;
    }
    setError(null);
    setSubmitting(true);
    onSubmit(values)
      .then((entry) => onSuccess(entry))
      .catch((err: unknown) => {
        const message = err instanceof JournalApiError ? err.message : "Не удалось сохранить запись.";
        setError(message);
      })
      .finally(() => setSubmitting(false));
  }

  return (
    <form className="journal-entry-form" onSubmit={handleSubmit}>
      <h3 className="journal-block-label">Моя сделка</h3>

      <label className="journal-field">
        Тикер
        <input
          type="text"
          value={values.ticker}
          disabled={submitting}
          onChange={(event) => setValues((prev) => ({ ...prev, ticker: event.target.value }))}
        />
      </label>

      <label className="journal-field">
        Направление
        <select
          value={values.direction}
          disabled={submitting}
          onChange={(event) =>
            setValues((prev) => ({ ...prev, direction: event.target.value as TradeDirection }))
          }
        >
          {DIRECTION_ORDER.map((direction) => (
            <option key={direction} value={direction}>
              {DIRECTION_LABELS[direction]}
            </option>
          ))}
        </select>
      </label>

      <label className="journal-field">
        Результат
        <select
          value={values.resultStatus}
          disabled={submitting}
          onChange={(event) =>
            setValues((prev) => ({ ...prev, resultStatus: event.target.value as TradeResultStatus }))
          }
        >
          {RESULT_STATUS_ORDER.map((resultStatus) => (
            <option key={resultStatus} value={resultStatus}>
              {RESULT_STATUS_LABELS[resultStatus]}
            </option>
          ))}
        </select>
      </label>

      <label className="journal-field">
        Комментарий (необязательно)
        <textarea
          value={values.resultNote}
          disabled={submitting}
          onChange={(event) => setValues((prev) => ({ ...prev, resultNote: event.target.value }))}
        />
      </label>

      {values.insightId !== null && (
        <div className="journal-linked-insight">
          <h3 className="journal-block-label">Связанный AI-инсайт</h3>
          <p className="journal-field-insight-link">
            Инсайт #{values.insightId} — контекст/основание, не команда AI.{" "}
            <button
              type="button"
              disabled={submitting}
              onClick={() => setValues((prev) => ({ ...prev, insightId: null }))}
            >
              Отвязать
            </button>
          </p>
        </div>
      )}

      {error && (
        <p className="journal-form-error" role="alert">
          {error}
        </p>
      )}

      <div className="journal-form-actions">
        <button type="submit" disabled={submitting}>
          {submitting ? "Сохранение…" : submitLabel}
        </button>
        <button type="button" disabled={submitting} onClick={onCancel}>
          Отмена
        </button>
      </div>
    </form>
  );
}
