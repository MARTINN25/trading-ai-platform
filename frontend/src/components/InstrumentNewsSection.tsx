"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getInstrumentNews,
  InstrumentApiError,
  type InstrumentNewsItem,
} from "@/lib/instrument-api";

type NewsState =
  | { status: "loading" }
  | { status: "loaded"; items: InstrumentNewsItem[] }
  | { status: "error"; message: string };

const publishedAtFormatter = new Intl.DateTimeFormat("ru-RU", {
  dateStyle: "medium",
  timeStyle: "short",
});

function formatPublishedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return publishedAtFormatter.format(date);
}

/**
 * Defense in depth (task scope §6, §14): the backend already rejects
 * anything but `http(s)://` before an item is ever constructed
 * (`news_gateway._validate_article_url`), but this is the last place
 * before a real `<a href>` — a genuinely malformed/unsafe URL here is
 * never rendered as a link.
 */
function isSafeArticleUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export default function InstrumentNewsSection({ ticker }: { ticker: string }) {
  const [state, setState] = useState<NewsState>({ status: "loading" });

  const load = useCallback(() => {
    setState({ status: "loading" });
    getInstrumentNews(ticker)
      .then((data) => setState({ status: "loaded", items: data.items }))
      .catch((error: unknown) => {
        const message =
          error instanceof InstrumentApiError ? error.message : "Новости сейчас недоступны.";
        setState({ status: "error", message });
      });
  }, [ticker]);

  useEffect(() => {
    // Loads exactly once per instrument page visit — no polling, no
    // refresh timer, no automatic retry (task scope §10).
    load();
  }, [load]);

  const safeItems = state.status === "loaded" ? state.items.filter((item) => isSafeArticleUrl(item.url)) : [];

  return (
    <section className="instrument-news-section" aria-labelledby="instrument-news-heading">
      <h2 id="instrument-news-heading">Новости</h2>

      <div aria-live="polite">
        {state.status === "loading" && <p className="instrument-news-loading">Загрузка новостей…</p>}

        {state.status === "error" && (
          <div className="instrument-news-error" role="alert">
            <p>{state.message}</p>
            <button type="button" onClick={load}>
              Повторить
            </button>
          </div>
        )}

        {state.status === "loaded" && safeItems.length === 0 && (
          <p className="instrument-news-empty">Свежих новостей по инструменту нет.</p>
        )}

        {state.status === "loaded" && safeItems.length > 0 && (
          <ul className="instrument-news-list">
            {safeItems.map((item) => (
              <li key={item.id} className="instrument-news-card">
                <h3 className="instrument-news-headline">{item.headline}</h3>
                {item.summary ? <p className="instrument-news-summary">{item.summary}</p> : null}
                <p className="instrument-news-meta">
                  {item.source} · {formatPublishedAt(item.published_at)}
                </p>
                <a
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="instrument-news-link"
                >
                  Открыть источник →
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
