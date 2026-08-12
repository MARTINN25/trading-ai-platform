"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getInstrumentNews,
  InstrumentApiError,
  type InstrumentNewsItem,
  type NewsRelationship,
  type NewsRelevance,
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

const RELEVANCE_LABELS: Record<NewsRelevance, string> = {
  high: "Высокая релевантность",
  medium: "Средняя релевантность",
  low: "Низкая релевантность",
};

const RELEVANCE_BADGE_CLASS: Record<NewsRelevance, string> = {
  high: "instrument-news-badge instrument-news-badge--relevance-high",
  medium: "instrument-news-badge instrument-news-badge--relevance-medium",
  low: "instrument-news-badge instrument-news-badge--relevance-low",
};

const RELATIONSHIP_LABELS: Record<NewsRelationship, string> = {
  company: "Компания",
  sector: "Сектор",
  market: "Рынок",
  macro: "Макро",
  indirect: "Косвенно",
  noise: "Шум",
};

type NewsTier = "top" | "context";

/**
 * Two visual tiers using only real, already-returned data — never an
 * invented ranking (task scope §12-§13). `tier="top"` gets the full
 * card (RU summary, why-it-matters, hypothesis, original headline, all
 * visible). `tier="context"` shows a clamped summary plus a collapsible
 * "Подробнее" for the same fields — nothing is hidden with no way to
 * reveal it, just deprioritized by default.
 */
function NewsCard({ item, tier }: { item: InstrumentNewsItem; tier: NewsTier }) {
  const isCompact = tier === "context";
  const hasExpandableDetail =
    isCompact && item.enriched && Boolean(item.why_it_matters || item.impact_hypothesis);

  return (
    <li className={`instrument-news-card instrument-news-card--${tier}`}>
      <div className="instrument-news-badges">
        {item.enriched ? (
          <>
            {item.relevance ? (
              <span className={RELEVANCE_BADGE_CLASS[item.relevance]}>
                {RELEVANCE_LABELS[item.relevance]}
              </span>
            ) : null}
            {item.relationship ? (
              <span className="instrument-news-badge instrument-news-badge--relationship">
                {RELATIONSHIP_LABELS[item.relationship]}
              </span>
            ) : null}
          </>
        ) : (
          <span className="instrument-news-badge instrument-news-badge--unenriched">
            Без AI-анализа
          </span>
        )}
      </div>

      {item.enriched && item.summary_ru ? (
        <>
          <p
            className={
              isCompact ? "instrument-news-summary-ru instrument-news-summary-ru--clamped" : "instrument-news-summary-ru"
            }
          >
            {item.summary_ru}
          </p>
          {!isCompact && item.why_it_matters ? (
            <p className="instrument-news-field">
              <span className="instrument-news-field-label">Почему важно: </span>
              {item.why_it_matters}
            </p>
          ) : null}
          {!isCompact && item.impact_hypothesis ? (
            <p className="instrument-news-field instrument-news-field--hypothesis">
              <span className="instrument-news-field-label">Возможное влияние (гипотеза): </span>
              {item.impact_hypothesis}
            </p>
          ) : null}
          {!isCompact && (
            <div className="instrument-news-original">
              <p className="instrument-news-original-label">Оригинал</p>
              <h3 className="instrument-news-headline">{item.headline}</h3>
            </div>
          )}
          {hasExpandableDetail && (
            <details className="instrument-news-more">
              <summary>Подробнее</summary>
              <div className="instrument-news-more-body">
                {item.why_it_matters ? (
                  <p className="instrument-news-field">
                    <span className="instrument-news-field-label">Почему важно: </span>
                    {item.why_it_matters}
                  </p>
                ) : null}
                {item.impact_hypothesis ? (
                  <p className="instrument-news-field instrument-news-field--hypothesis">
                    <span className="instrument-news-field-label">Возможное влияние (гипотеза): </span>
                    {item.impact_hypothesis}
                  </p>
                ) : null}
                <div className="instrument-news-original">
                  <p className="instrument-news-original-label">Оригинал</p>
                  <h3 className="instrument-news-headline">{item.headline}</h3>
                </div>
              </div>
            </details>
          )}
        </>
      ) : (
        <h3 className="instrument-news-headline">{item.headline}</h3>
      )}

      {!item.enriched && item.summary ? (
        <p className="instrument-news-summary">{item.summary}</p>
      ) : null}

      <p className="instrument-news-meta">
        {item.source} · {formatPublishedAt(item.published_at)}
      </p>
      <a href={item.url} target="_blank" rel="noopener noreferrer" className="instrument-news-link">
        Открыть источник →
      </a>
    </li>
  );
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
  const anyEnriched = safeItems.some((item) => item.enriched);
  const allDegraded = safeItems.length > 0 && !anyEnriched;

  // Tiering uses only the backend's own `relevance` flag and preserves
  // its existing relative order in both groups — never a client-side
  // re-ranking (task scope §12). Capped at 2 "top" items so the
  // highlighted tier stays a highlight, not most of the list.
  const MAX_TOP_ITEMS = 2;
  const topItems: InstrumentNewsItem[] = [];
  const contextItems: InstrumentNewsItem[] = [];
  for (const item of safeItems) {
    if (item.relevance === "high" && topItems.length < MAX_TOP_ITEMS) {
      topItems.push(item);
    } else {
      contextItems.push(item);
    }
  }

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
          <p className="instrument-news-empty">Нет достаточно релевантных новостей.</p>
        )}

        {state.status === "loaded" && allDegraded && (
          <p className="instrument-news-degraded-notice">
            AI-объяснение сейчас недоступно — показаны исходные новости без анализа.
          </p>
        )}

        {state.status === "loaded" && topItems.length > 0 && (
          <>
            <h3 className="instrument-news-tier-title">Топ-новости</h3>
            <ul className="instrument-news-list instrument-news-list--top">
              {topItems.map((item) => (
                <NewsCard key={item.id} item={item} tier="top" />
              ))}
            </ul>
          </>
        )}

        {state.status === "loaded" && contextItems.length > 0 && (
          <>
            {topItems.length > 0 && <h3 className="instrument-news-tier-title">Дополнительный контекст</h3>}
            <ul className="instrument-news-list instrument-news-list--context">
              {contextItems.map((item) => (
                <NewsCard key={item.id} item={item} tier="context" />
              ))}
            </ul>
          </>
        )}
      </div>
    </section>
  );
}
