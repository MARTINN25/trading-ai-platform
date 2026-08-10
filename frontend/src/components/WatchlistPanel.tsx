"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  addWatchlistItem,
  getWatchlistQuotes,
  removeWatchlistItem,
  WatchlistApiError,
  type WatchlistItemQuote,
} from "@/lib/watchlist-api";

type ListState =
  | { status: "loading" }
  | { status: "loaded"; items: WatchlistItemQuote[] }
  | { status: "error"; message: string };

type FormErrorKind = "duplicate" | "invalid" | "unexpected" | null;

const createdAtFormatter = new Intl.DateTimeFormat("ru-RU", {
  dateStyle: "medium",
  timeStyle: "short",
});

const asOfFormatter = new Intl.DateTimeFormat("ru-RU", { timeStyle: "short" });

function formatCreatedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return createdAtFormatter.format(date);
}

function formatAsOf(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return asOfFormatter.format(date);
}

function parseNumber(value: string): number | null {
  const num = Number(value);
  return Number.isNaN(num) ? null : num;
}

function formatPrice(value: string): string | null {
  const num = parseNumber(value);
  if (num === null) {
    return null;
  }
  return `$${num.toLocaleString("ru-RU", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

interface FormattedChange {
  text: string;
  direction: "up" | "down" | "flat";
}

function formatChange(change: string, changePercent: string): FormattedChange | null {
  const changeNum = parseNumber(change);
  const percentNum = parseNumber(changePercent);
  if (changeNum === null || percentNum === null) {
    return null;
  }
  // Never color-only (task scope): the +/- sign is always present in
  // the text itself, not just conveyed by a CSS color.
  const sign = changeNum > 0 ? "+" : changeNum < 0 ? "" : "±";
  const percentSign = percentNum > 0 ? "+" : percentNum < 0 ? "" : "±";
  const direction = changeNum > 0 ? "up" : changeNum < 0 ? "down" : "flat";
  return {
    text: `${sign}${changeNum.toFixed(2)} (${percentSign}${percentNum.toFixed(2)}%)`,
    direction,
  };
}

export default function WatchlistPanel() {
  const [listState, setListState] = useState<ListState>({ status: "loading" });
  const [ticker, setTicker] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formErrorKind, setFormErrorKind] = useState<FormErrorKind>(null);
  const [formErrorMessage, setFormErrorMessage] = useState<string | null>(null);
  const [removingId, setRemovingId] = useState<number | null>(null);
  const [deleteErrorMessage, setDeleteErrorMessage] = useState<string | null>(null);

  // Single "load" function drives initial load, the manual "Обновить
  // данные" button, error retry, and the reload after a successful
  // add/delete (task scope: manual/one-shot loading, no auto-refresh
  // polling).
  const loadWatchlist = useCallback(() => {
    setListState({ status: "loading" });
    getWatchlistQuotes()
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
      await addWatchlistItem(trimmed);
      setTicker("");
      // Reload (not a local splice): the new item needs its quote
      // fetched too, and this endpoint returns items+quotes together.
      loadWatchlist();
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
      // Only reload after a confirmed 204 — no optimistic removal
      // (backend stays source of truth).
      loadWatchlist();
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
      <div className="watchlist-heading-row">
        <h2 id="watchlist-heading">Watchlist</h2>
        {listState.status === "loaded" ? (
          <button type="button" className="watchlist-refresh-button" onClick={loadWatchlist}>
            Обновить данные
          </button>
        ) : null}
      </div>

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
            {listState.items.map((item) => {
              const price = item.price !== null ? formatPrice(item.price) : null;
              const change =
                item.change !== null && item.change_percent !== null
                  ? formatChange(item.change, item.change_percent)
                  : null;
              const quoteAvailable = item.quote_error === null && price !== null && change !== null;

              return (
                <li key={item.id}>
                  <div className="watchlist-row-main">
                    <span className="watchlist-ticker">{item.ticker}</span>
                    <span className="watchlist-created-at">
                      {formatCreatedAt(item.created_at)}
                    </span>
                    <button
                      type="button"
                      className="watchlist-remove-button"
                      onClick={() => handleRemove(item.id)}
                      disabled={removingId === item.id}
                      aria-label={`Удалить ${item.ticker} из watchlist`}
                    >
                      {removingId === item.id ? "Удаление…" : "Удалить"}
                    </button>
                  </div>
                  <div className="watchlist-quote">
                    {quoteAvailable && price !== null && change !== null ? (
                      <>
                        <span className="watchlist-quote-price">{price}</span>
                        <span
                          className={`watchlist-quote-change watchlist-quote-change-${change.direction}`}
                          aria-label={
                            change.direction === "up"
                              ? "рост"
                              : change.direction === "down"
                                ? "падение"
                                : "без изменений"
                          }
                        >
                          {change.text}
                        </span>
                        {item.as_of ? (
                          <span className="watchlist-quote-as-of">
                            Обновлено: {formatAsOf(item.as_of)}
                          </span>
                        ) : null}
                      </>
                    ) : (
                      <span className="watchlist-quote-unavailable">Данные недоступны</span>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        {deleteErrorMessage ? (
          <p className="watchlist-delete-error" role="alert">
            {deleteErrorMessage}
          </p>
        ) : null}
      </div>

      <p className="watchlist-disclaimer">
        Рыночные данные — только для просмотра и могут запаздывать; это не торговое исполнение
        и не рекомендация.
      </p>
    </section>
  );
}
