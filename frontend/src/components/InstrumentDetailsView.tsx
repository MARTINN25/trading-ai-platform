"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  getInstrumentDetails,
  InstrumentApiError,
  type InstrumentDetails,
} from "@/lib/instrument-api";
import PriceChartSection from "@/components/PriceChartSection";
import InstrumentNewsSection from "@/components/InstrumentNewsSection";
import AiAnalysisSection from "@/components/AiAnalysisSection";
import InsightHistorySection from "@/components/InsightHistorySection";

type ViewState =
  | { status: "loading" }
  | { status: "loaded"; data: InstrumentDetails }
  | { status: "error"; message: string };

const asOfFormatter = new Intl.DateTimeFormat("ru-RU", {
  dateStyle: "medium",
  timeStyle: "short",
});

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

function formatPrice(value: string | null): string | null {
  if (value === null) {
    return null;
  }
  const num = parseNumber(value);
  if (num === null) {
    return null;
  }
  return `$${num.toLocaleString("ru-RU", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function formatVolume(value: number | null): string | null {
  if (value === null) {
    return null;
  }
  return value.toLocaleString("ru-RU");
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
  // Never color-only: the +/- sign is always in the text itself, not
  // just conveyed by CSS color (same rule as WatchlistPanel).
  const sign = changeNum > 0 ? "+" : changeNum < 0 ? "" : "±";
  const percentSign = percentNum > 0 ? "+" : percentNum < 0 ? "" : "±";
  const direction = changeNum > 0 ? "up" : changeNum < 0 ? "down" : "flat";
  return {
    text: `${sign}${changeNum.toFixed(2)} (${percentSign}${percentNum.toFixed(2)}%)`,
    direction,
  };
}

const UNAVAILABLE = "Данные недоступны";

const SOURCE_DISPLAY_NAMES: Record<string, string> = {
  twelvedata: "Twelve Data",
};

function formatSource(source: string): string {
  return SOURCE_DISPLAY_NAMES[source] ?? source;
}

/**
 * Instrument Workspace (Phase 1, task scope §7) — reorganizes the same
 * five data sections (quote/stats, chart, news, AI analysis, history)
 * into a dense, entity-centric workspace instead of a single narrow
 * column. `PriceChartSection`/`InstrumentNewsSection`/
 * `AiAnalysisSection`/`InsightHistorySection` are unchanged internally
 * — only their composition (grid placement) changes here.
 */
export default function InstrumentDetailsView({ ticker }: { ticker: string }) {
  const [state, setState] = useState<ViewState>({ status: "loading" });
  // Bumped by `AiAnalysisSection` right after a successful save — the
  // one explicit bridge between the two otherwise-independent AI
  // sections, so the history list reloads without becoming a shared
  // page-level state (task scope §14-§16 of the earlier insight-
  // persistence task).
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);

  const load = useCallback(() => {
    setState({ status: "loading" });
    getInstrumentDetails(ticker)
      .then((data) => setState({ status: "loaded", data }))
      .catch((error: unknown) => {
        const message =
          error instanceof InstrumentApiError
            ? error.message
            : "Не удалось загрузить данные инструмента.";
        setState({ status: "error", message });
      });
  }, [ticker]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <main className="instrument-workspace">
      <nav className="workspace-breadcrumb" aria-label="Навигация по разделу">
        <Link href="/" className="workspace-breadcrumb-link">
          Обзор
        </Link>
        <span aria-hidden="true">/</span>
        <Link href="/markets" className="workspace-breadcrumb-link">
          Рынки
        </Link>
        <span aria-hidden="true">/</span>
        <span className="workspace-breadcrumb-current">{ticker}</span>
      </nav>

      <div aria-live="polite">
        {state.status === "loading" && <p>Загрузка данных по {ticker}…</p>}

        {state.status === "error" && (
          <div className="instrument-details-error" role="alert">
            <p>{state.message}</p>
            <button type="button" onClick={load}>
              Повторить
            </button>
          </div>
        )}

        {state.status === "loaded" && <InstrumentHeader data={state.data} />}
      </div>

      {/* B/C. Chart gets the wide primary column; stats sit beside it
          as a compact panel (task scope §7). Independent of the
          summary's own loading/error state above — a chart failure
          never hides an already-loaded summary, and vice versa. */}
      <div className="workspace-primary-row">
        <section className="workspace-panel workspace-chart-panel" aria-label="График цены">
          <PriceChartSection ticker={ticker} />
        </section>
        <aside className="workspace-panel workspace-stats-panel" aria-label="Рыночная статистика">
          <h2>Статистика</h2>
          {state.status === "loaded" ? (
            <InstrumentStatsPanel data={state.data} />
          ) : (
            <p className="text-muted">{state.status === "loading" ? "Загрузка…" : UNAVAILABLE}</p>
          )}
        </aside>
      </div>

      {/* D. News + AI analysis side by side — reduces vertical
          scrolling to reach the AI section (task scope §7). Each
          section still owns its own independent loading/error state,
          same rule as before. */}
      <div className="workspace-intelligence-row">
        <section className="workspace-panel workspace-news-panel">
          <InstrumentNewsSection ticker={ticker} />
        </section>
        <section className="workspace-panel workspace-ai-panel">
          <AiAnalysisSection
            ticker={ticker}
            onInsightSaved={() => setHistoryRefreshKey((key) => key + 1)}
          />
        </section>
      </div>

      {/* E. History remains reachable without dominating the initial
          viewport — a full-width panel below the fold, same
          independent loading/error/empty state as before. */}
      <section className="workspace-history-panel">
        <InsightHistorySection ticker={ticker} refreshKey={historyRefreshKey} />
      </section>

      <p className="instrument-disclaimer">
        Рыночные данные — только для просмотра и могут запаздывать; это не торговое исполнение и
        не рекомендация.
      </p>
    </main>
  );
}

function InstrumentHeader({ data }: { data: InstrumentDetails }) {
  const price = formatPrice(data.price);
  const change = formatChange(data.change, data.change_percent);

  return (
    <header className="instrument-header">
      <h1 className="instrument-ticker">{data.ticker}</h1>
      <p className="instrument-price">{price ?? UNAVAILABLE}</p>
      {change ? (
        <p
          className={`instrument-change instrument-change-${change.direction}`}
          aria-label={
            change.direction === "up" ? "рост" : change.direction === "down" ? "падение" : "без изменений"
          }
        >
          {change.text}
        </p>
      ) : (
        <p className="instrument-change-unavailable">{UNAVAILABLE}</p>
      )}
      <div className="instrument-header-meta">
        <span>Обновлено: {formatAsOf(data.as_of)}</span>
        <span>Источник: {formatSource(data.source)}</span>
      </div>
    </header>
  );
}

function InstrumentStatsPanel({ data }: { data: InstrumentDetails }) {
  const stats: Array<{ label: string; value: string | null }> = [
    { label: "Open", value: formatPrice(data.open) },
    { label: "High", value: formatPrice(data.high) },
    { label: "Low", value: formatPrice(data.low) },
    { label: "Previous close", value: formatPrice(data.previous_close) },
    { label: "Volume", value: formatVolume(data.volume) },
  ];

  return (
    <dl className="instrument-stats-grid">
      {stats.map((stat) => (
        <div className="instrument-stat" key={stat.label}>
          <dt className="instrument-stat-label">{stat.label}</dt>
          <dd className="instrument-stat-value">{stat.value ?? UNAVAILABLE}</dd>
        </div>
      ))}
      <div className="instrument-stat">
        <dt className="instrument-stat-label">Source</dt>
        <dd className="instrument-stat-value">{formatSource(data.source)}</dd>
      </div>
    </dl>
  );
}
