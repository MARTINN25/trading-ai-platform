"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import WatchlistPanel from "@/components/WatchlistPanel";
import {
  getRecentInsights,
  InstrumentApiError,
  type InsightSummary,
  type InstrumentConfidenceLevel,
} from "@/lib/instrument-api";
import { getJournalEntries, JournalApiError, type JournalEntry } from "@/lib/journal-api";

/**
 * Overview (Phase 1, task scope §5) — replaces the previous bare
 * watchlist-only home page. Only real, already-available data: the
 * existing watchlist (via `WatchlistPanel`, reused unchanged) plus
 * recent insights/journal activity through already-approved read
 * endpoints. No fabricated market breadth, indices, macro, sentiment,
 * alerts, or signals (task scope §5) — those categories are UNRESOLVED/
 * FUTURE per `TARGET_INTELLIGENCE_CONTEXT.md` and are not invented here.
 */

const RECENT_INSIGHTS_LIMIT = 5;
const RECENT_JOURNAL_LIMIT = 5;

type InsightsState =
  | { status: "loading" }
  | { status: "loaded"; items: InsightSummary[] }
  | { status: "error"; message: string };

type JournalState =
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

const CONFIDENCE_LABELS: Record<InstrumentConfidenceLevel, string> = {
  high: "Высокая",
  medium: "Средняя",
  low: "Низкая",
};

const DIRECTION_LABELS: Record<JournalEntry["direction"], string> = {
  long: "Лонг",
  short: "Шорт",
};

const RESULT_STATUS_LABELS: Record<JournalEntry["result_status"], string> = {
  profit: "Прибыльная",
  loss: "Убыточная",
  breakeven: "Безубыточная",
  open: "В процессе",
};

export default function OverviewView() {
  const [insights, setInsights] = useState<InsightsState>({ status: "loading" });
  const [journal, setJournal] = useState<JournalState>({ status: "loading" });

  useEffect(() => {
    getRecentInsights(RECENT_INSIGHTS_LIMIT)
      .then((data) => setInsights({ status: "loaded", items: data.items }))
      .catch((error: unknown) => {
        const message =
          error instanceof InstrumentApiError ? error.message : "Не удалось загрузить инсайты.";
        setInsights({ status: "error", message });
      });
  }, []);

  useEffect(() => {
    getJournalEntries()
      .then((items) => setJournal({ status: "loaded", items: items.slice(0, RECENT_JOURNAL_LIMIT) }))
      .catch((error: unknown) => {
        const message =
          error instanceof JournalApiError ? error.message : "Не удалось загрузить дневник.";
        setJournal({ status: "error", message });
      });
  }, []);

  return (
    <main className="overview">
      <header className="overview-header">
        <div>
          <h1>Обзор</h1>
          <p className="overview-subtitle">
            Инструменты, за которыми вы следите (Watchlist), последние AI-инсайты по ним и ваши
            последние записи в дневнике сделок — в одном месте.
          </p>
        </div>
        <Link href="/markets" className="btn btn-primary overview-markets-link">
          Перейти к рынкам →
        </Link>
      </header>

      <div className="overview-grid">
        <section className="overview-panel" aria-labelledby="overview-watchlist-heading">
          <WatchlistPanel />
        </section>

        <div className="overview-side">
          <section className="overview-panel" aria-labelledby="overview-insights-heading">
            <h2 id="overview-insights-heading">Последние AI-инсайты</h2>
            <p className="overview-panel-hint">
              Сохранённые AI-анализы по вашим инструментам — справочная информация, не торговые
              команды.
            </p>

            <div aria-live="polite">
              {insights.status === "loading" && (
                <p className="overview-loading">Загрузка…</p>
              )}

              {insights.status === "error" && (
                <p className="overview-error" role="alert">
                  {insights.message}
                </p>
              )}

              {insights.status === "loaded" && insights.items.length === 0 && (
                <p className="overview-empty">
                  Сохранённых инсайтов пока нет. Откройте инструмент и сгенерируйте AI-анализ.
                </p>
              )}

              {insights.status === "loaded" && insights.items.length > 0 && (
                <ul className="overview-list">
                  {insights.items.map((item) => (
                    <li key={item.id} className="overview-list-item">
                      <p className="overview-list-item-meta">
                        <Link
                          href={`/instruments/${encodeURIComponent(item.ticker)}`}
                          className="overview-list-item-ticker"
                        >
                          {item.ticker}
                        </Link>
                        <span>{formatTimestamp(item.created_at)}</span>
                        <span>Уверенность: {CONFIDENCE_LABELS[item.confidence]}</span>
                      </p>
                      <p className="overview-list-item-summary">{item.summary}</p>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <Link href="/insights" className="overview-see-all">
              Вся история →
            </Link>
          </section>

          <section className="overview-panel" aria-labelledby="overview-journal-heading">
            <h2 id="overview-journal-heading">Последние записи дневника</h2>
            <p className="overview-panel-hint">Сделки, которые вы зафиксировали вручную.</p>

            <div aria-live="polite">
              {journal.status === "loading" && <p className="overview-loading">Загрузка…</p>}

              {journal.status === "error" && (
                <p className="overview-error" role="alert">
                  {journal.message}
                </p>
              )}

              {journal.status === "loaded" && journal.items.length === 0 && (
                <p className="overview-empty">Записей в дневнике пока нет.</p>
              )}

              {journal.status === "loaded" && journal.items.length > 0 && (
                <ul className="overview-list">
                  {journal.items.map((entry) => (
                    <li key={entry.id} className="overview-list-item">
                      <p className="overview-list-item-meta">
                        <Link
                          href={`/instruments/${encodeURIComponent(entry.ticker)}`}
                          className="overview-list-item-ticker"
                        >
                          {entry.ticker}
                        </Link>
                        <span>{DIRECTION_LABELS[entry.direction]}</span>
                        <span>{RESULT_STATUS_LABELS[entry.result_status]}</span>
                        <span>{formatTimestamp(entry.created_at)}</span>
                      </p>
                      {entry.result_note && (
                        <p className="overview-list-item-summary">{entry.result_note}</p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <Link href="/journal" className="overview-see-all">
              Весь дневник →
            </Link>
          </section>
        </div>
      </div>
    </main>
  );
}
