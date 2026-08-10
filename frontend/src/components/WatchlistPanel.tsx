"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  addWatchlistItem,
  getWatchlist,
  removeWatchlistItem,
  WatchlistApiError,
  type WatchlistItem,
} from "@/lib/watchlist-api";

type ListState =
  | { status: "loading" }
  | { status: "loaded"; items: WatchlistItem[] }
  | { status: "error"; message: string };

type FormErrorKind = "duplicate" | "invalid" | "unexpected" | null;

const createdAtFormatter = new Intl.DateTimeFormat("ru-RU", {
  dateStyle: "medium",
  timeStyle: "short",
});

function formatCreatedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return createdAtFormatter.format(date);
}

export default function WatchlistPanel() {
  const [listState, setListState] = useState<ListState>({ status: "loading" });
  const [ticker, setTicker] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formErrorKind, setFormErrorKind] = useState<FormErrorKind>(null);
  const [formErrorMessage, setFormErrorMessage] = useState<string | null>(null);
  const [removingId, setRemovingId] = useState<number | null>(null);
  const [deleteErrorMessage, setDeleteErrorMessage] = useState<string | null>(null);

  const loadWatchlist = useCallback(() => {
    setListState({ status: "loading" });
    getWatchlist()
      .then((items) => setListState({ status: "loaded", items }))
      .catch((error: unknown) => {
        const message =
          error instanceof WatchlistApiError
            ? error.message
            : "Не удалось загрузить watchlist.";
        setListState({ status: "error", message });
      });
  }, []);

  useEffect(() => {
    loadWatchlist();
  }, [loadWatchlist]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const trimmed = ticker.trim();
    if (!trimmed) {
      setFormErrorKind("invalid");
      setFormErrorMessage("Введите тикер.");
      return;
    }

    setSubmitting(true);
    setFormErrorKind(null);
    setFormErrorMessage(null);

    try {
      const item = await addWatchlistItem(trimmed);
      setTicker("");
      setListState((previous) =>
        previous.status === "loaded"
          ? { status: "loaded", items: [...previous.items, item] }
          : { status: "loaded", items: [item] }
      );
    } catch (error) {
      if (error instanceof WatchlistApiError) {
        setFormErrorKind(
          error.kind === "duplicate" || error.kind === "invalid" ? error.kind : "unexpected"
        );
        setFormErrorMessage(error.message);
      } else {
        setFormErrorKind("unexpected");
        setFormErrorMessage("Не удалось добавить тикер.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRemove(id: number): Promise<void> {
    setRemovingId(id);
    setDeleteErrorMessage(null);

    try {
      await removeWatchlistItem(id);
      // Only remove from local state after a confirmed 204 — no
      // optimistic removal (backend stays source of truth).
      setListState((previous) =>
        previous.status === "loaded"
          ? { status: "loaded", items: previous.items.filter((item) => item.id !== id) }
          : previous
      );
    } catch (error) {
      setDeleteErrorMessage(
        error instanceof WatchlistApiError ? error.message : "Не удалось удалить тикер."
      );
    } finally {
      setRemovingId(null);
    }
  }

  return (
    <section className="watchlist" aria-labelledby="watchlist-heading">
      <h2 id="watchlist-heading">Watchlist</h2>

      <form className="watchlist-form" onSubmit={handleSubmit} noValidate>
        <label htmlFor="ticker-input">Тикер</label>
        <div className="watchlist-form-row">
          <input
            id="ticker-input"
            name="ticker"
            type="text"
            value={ticker}
            onChange={(event) => setTicker(event.target.value.toUpperCase())}
            placeholder="Например, AAPL"
            disabled={submitting}
            autoComplete="off"
          />
          <button type="submit" disabled={submitting}>
            {submitting ? "Добавление…" : "Добавить"}
          </button>
        </div>
        {formErrorMessage ? (
          <p
            className="watchlist-form-error"
            role="alert"
            data-error-kind={formErrorKind ?? undefined}
          >
            {formErrorMessage}
          </p>
        ) : null}
      </form>

      <div aria-live="polite">
        {listState.status === "loading" && <p>Загрузка watchlist…</p>}

        {listState.status === "error" && (
          <div className="watchlist-list-error" role="alert">
            <p>{listState.message}</p>
            <button type="button" onClick={loadWatchlist}>
              Повторить
            </button>
          </div>
        )}

        {listState.status === "loaded" && listState.items.length === 0 && (
          <p>Watchlist пуст. Добавьте первый тикер выше.</p>
        )}

        {listState.status === "loaded" && listState.items.length > 0 && (
          <ul className="watchlist-list">
            {listState.items.map((item) => (
              <li key={item.id}>
                <span className="watchlist-ticker">{item.ticker}</span>
                <span className="watchlist-created-at">{formatCreatedAt(item.created_at)}</span>
                <button
                  type="button"
                  className="watchlist-remove-button"
                  onClick={() => handleRemove(item.id)}
                  disabled={removingId === item.id}
                  aria-label={`Удалить ${item.ticker} из watchlist`}
                >
                  {removingId === item.id ? "Удаление…" : "Удалить"}
                </button>
              </li>
            ))}
          </ul>
        )}

        {deleteErrorMessage ? (
          <p className="watchlist-delete-error" role="alert">
            {deleteErrorMessage}
          </p>
        ) : null}
      </div>
    </section>
  );
}
