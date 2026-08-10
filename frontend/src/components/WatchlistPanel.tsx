"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import Link from "next/link";
import {
  addWatchlistItem,
  getWatchlistQuotes,
  removeWatchlistItem,
  WatchlistApiError,
  type WatchlistItemQuote,
} from "@/lib/watchlist-api";
import { searchInstruments, InstrumentApiError, type InstrumentSearchResult } from "@/lib/instrument-api";

type ListState =
  | { status: "loading" }
  | { status: "loaded"; items: WatchlistItemQuote[] }
  | { status: "error"; message: string };

type FormErrorKind = "duplicate" | "invalid" | "unexpected" | null;

type SearchState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "loaded"; items: InstrumentSearchResult[] }
  | { status: "error"; message: string };

// Task scope §7, §9: fewer than this many characters is too
// unspecific to be worth a provider request — no search fires below
// it, matching the backend's own `MIN_SEARCH_QUERY_LENGTH`.
const MIN_SEARCH_QUERY_LENGTH = 2;
const SEARCH_DEBOUNCE_MS = 300;

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

  // Search-as-you-type state — separate from the exact-ticker form
  // state above, since the input now serves both roles (task scope
  // §3: adapt the existing field, don't replace it).
  const [searchState, setSearchState] = useState<SearchState>({ status: "idle" });
  const [resultsVisible, setResultsVisible] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const abortControllerRef = useRef<AbortController | null>(null);

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

  // Debounced search-as-you-type (task scope §7, §9): no request below
  // MIN_SEARCH_QUERY_LENGTH, no request per keypress, at most one
  // settled-query request via the timer below. The effect's own
  // cleanup — which React runs before every re-run and on unmount —
  // both cancels a not-yet-fired timer and aborts an already-in-flight
  // fetch, so a stale response from a superseded query can never
  // overwrite a newer one (the aborted fetch's promise rejects with
  // `AbortError`, which the `.catch` below silently ignores).
  useEffect(() => {
    const trimmed = ticker.trim();

    if (trimmed.length < MIN_SEARCH_QUERY_LENGTH) {
      setSearchState({ status: "idle" });
      setResultsVisible(false);
      return;
    }

    const timer = setTimeout(() => {
      const controller = new AbortController();
      abortControllerRef.current = controller;
      setSearchState({ status: "loading" });
      setResultsVisible(true);
      searchInstruments(trimmed, controller.signal)
        .then((response) => {
          setSearchState({ status: "loaded", items: response.items });
          setHighlightedIndex(-1);
        })
        .catch((error: unknown) => {
          if (error instanceof DOMException && error.name === "AbortError") {
            return;
          }
          const message =
            error instanceof InstrumentApiError ? error.message : "Не удалось выполнить поиск.";
          setSearchState({ status: "error", message });
        });
    }, SEARCH_DEBOUNCE_MS);

    return () => {
      clearTimeout(timer);
      abortControllerRef.current?.abort();
      abortControllerRef.current = null;
    };
  }, [ticker]);

  async function addTicker(rawTicker: string): Promise<void> {
    setSubmitting(true);
    setFormErrorKind(null);
    setFormErrorMessage(null);

    try {
      await addWatchlistItem(rawTicker);
      setTicker("");
      setSearchState({ status: "idle" });
      setResultsVisible(false);
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

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const trimmed = ticker.trim();
    if (!trimmed) {
      setFormErrorKind("invalid");
      setFormErrorMessage("Введите тикер.");
      return;
    }
    await addTicker(trimmed);
  }

  async function handleSelectResult(result: InstrumentSearchResult): Promise<void> {
    setResultsVisible(false);
    await addTicker(result.ticker);
  }

  function handleInputKeyDown(event: KeyboardEvent<HTMLInputElement>): void {
    if (searchState.status !== "loaded" || !resultsVisible || searchState.items.length === 0) {
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlightedIndex((prev) => Math.min(prev + 1, searchState.items.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlightedIndex((prev) => Math.max(prev - 1, 0));
    } else if (event.key === "Enter" && highlightedIndex >= 0) {
      // Only intercept Enter when a result is actually highlighted —
      // otherwise it falls through to the form's onSubmit, preserving
      // exact-ticker entry as a fallback (task scope §3, §7).
      event.preventDefault();
      void handleSelectResult(searchState.items[highlightedIndex]);
    } else if (event.key === "Escape") {
      event.preventDefault();
      setResultsVisible(false);
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

      <form className="watchlist-form" onSubmit={handleSubmit} noValidate autoComplete="off">
        <label htmlFor="ticker-input">Тикер или название</label>
        <div className="watchlist-form-row">
          <input
            id="ticker-input"
            name="ticker"
            type="text"
            value={ticker}
            onChange={(event) => setTicker(event.target.value)}
            onKeyDown={handleInputKeyDown}
            onFocus={() => {
              if (searchState.status === "loaded" && searchState.items.length > 0) {
                setResultsVisible(true);
              }
            }}
            onBlur={() => setResultsVisible(false)}
            placeholder="Например, Apple или AAPL"
            disabled={submitting}
            autoComplete="off"
            role="combobox"
            aria-expanded={resultsVisible}
            aria-autocomplete="list"
            aria-controls="watchlist-search-results"
          />
          <button type="submit" disabled={submitting}>
            {submitting ? "Добавление…" : "Добавить"}
          </button>

          {resultsVisible ? (
            <div
              className="watchlist-search-results"
              id="watchlist-search-results"
              role="listbox"
            >
              {searchState.status === "loading" && (
                <p className="watchlist-search-loading">Поиск…</p>
              )}

              {searchState.status === "error" && (
                <p className="watchlist-search-error" role="alert">
                  {searchState.message}
                </p>
              )}

              {searchState.status === "loaded" && searchState.items.length === 0 && (
                <p className="watchlist-search-empty">Ничего не найдено.</p>
              )}

              {searchState.status === "loaded" && searchState.items.length > 0 && (
                <>
                  <ul>
                    {searchState.items.map((result, index) => {
                      const meta = [result.exchange, result.currency]
                        .filter((part): part is string => Boolean(part))
                        .join(" · ");
                      return (
                        <li
                          key={`${result.ticker}-${result.exchange ?? ""}-${index}`}
                          role="option"
                          aria-selected={index === highlightedIndex}
                          className={
                            index === highlightedIndex
                              ? "watchlist-search-result watchlist-search-result-highlighted"
                              : "watchlist-search-result"
                          }
                          onMouseDown={(event) => event.preventDefault()}
                          onClick={() => void handleSelectResult(result)}
                          onMouseEnter={() => setHighlightedIndex(index)}
                        >
                          <span className="watchlist-search-result-ticker">{result.ticker}</span>
                          <span className="watchlist-search-result-name">{result.name}</span>
                          {meta ? (
                            <span className="watchlist-search-result-meta">{meta}</span>
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                  <p className="watchlist-search-hint">
                    В watchlist сохраняется только тикер, без привязки к бирже. Биржа и валюта
                    показаны, чтобы отличить нужный инструмент от похожих тикеров.
                  </p>
                </>
              )}
            </div>
          ) : null}
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
                    <Link
                      href={`/instruments/${encodeURIComponent(item.ticker)}`}
                      className="watchlist-ticker"
                    >
                      {item.ticker}
                    </Link>
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
