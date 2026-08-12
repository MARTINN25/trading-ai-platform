"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  getInstrumentDetails,
  InstrumentApiError,
  type InstrumentDetails,
} from "@/lib/instrument-api";
import PriceChartSection, { type ActivePeriodHistory } from "@/components/PriceChartSection";
import MarketSnapshotPanel from "@/components/MarketSnapshotPanel";
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

interface Freshness {
  label: string;
  stale: boolean;
}

// Derived purely from the already-fetched `as_of` timestamp — no new
// field, no fabricated freshness metric. `STALE_THRESHOLD_MINUTES` is a
// restrained, visible-but-not-alarming signal (task scope §4), not a
// claim about real market-session staleness rules.
const STALE_THRESHOLD_MINUTES = 15;

function formatFreshness(value: string): Freshness {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return { label: UNAVAILABLE, stale: false };
  }
  const ageMinutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));
  const stale = ageMinutes > STALE_THRESHOLD_MINUTES;
  const label = ageMinutes < 1 ? "обновлено только что" : `обновлено ${ageMinutes} мин назад`;
  return { label, stale };
}

/**
 * Professional Instrument Workspace (Phase 2B.1) — information
 * hierarchy: header -> primary market panel (chart + market snapshot)
 * -> forecast panel (full width, own row) -> intelligence row (news)
 * -> history. Phase 1 originally put News and AI side by side in one
 * row; this task gives Forecast its own full-width row instead, since
 * a multi-screen-tall AI column no longer leaves a half-empty News
 * column beside it. `PriceChartSection`/`InstrumentNewsSection`/
 * `AiAnalysisSection`/`InsightHistorySection` remain independently
 * responsible for their own data fetching — only composition
 * (placement) changes here, plus the new `MarketSnapshotPanel` reading
 * `PriceChartSection`'s already-loaded period data.
 */
export default function InstrumentDetailsView({ ticker }: { ticker: string }) {
  const [state, setState] = useState<ViewState>({ status: "loading" });
  // Bumped by `AiAnalysisSection` right after a successful save — the
  // one explicit bridge between the two otherwise-independent AI
  // sections, so the history list reloads without becoming a shared
  // page-level state (task scope §14-§16 of the earlier insight-
  // persistence task).
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);
  // Reported by `PriceChartSection` (task scope §9) — read-only, so
  // the market snapshot can derive period high/low without a second,
  // duplicate history fetch; `PriceChartSection` still owns its own
  // loading/error state entirely.
  const [periodHistory, setPeriodHistory] = useState<ActivePeriodHistory | null>(null);

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

      {/* PRIMARY MARKET PANEL — chart gets the wide primary column;
          the market snapshot sits beside it as a compact panel
          (Professional Instrument Workspace, task scope §4). The
          snapshot's period-range half is populated from the chart's
          own already-loaded data (`onActivePeriodHistoryChange`), no
          second fetch. Independent of the header's own loading/error
          state above — a chart failure never hides an already-loaded
          header, and vice versa. */}
      <div className="workspace-primary-row">
        <section className="workspace-panel workspace-chart-panel" aria-label="График цены">
          <PriceChartSection ticker={ticker} onActivePeriodHistoryChange={setPeriodHistory} />
        </section>
        <aside className="workspace-panel workspace-stats-panel" aria-label="Рыночный снимок">
          <h2>Рыночный снимок</h2>
          {state.status === "loaded" ? (
            <MarketSnapshotPanel data={state.data} periodHistory={periodHistory} />
          ) : (
            <p className="text-muted">{state.status === "loading" ? "Загрузка…" : UNAVAILABLE}</p>
          )}
        </aside>
      </div>

      {/* FORECAST PANEL — full width of its own row: the previous
          layout squeezed a long AI column into a narrow half next to
          News, forcing multi-screen scrolling while the other column
          sat empty (task scope §4). `AiAnalysisSection` owns the
          horizon selector, `ForecastCard`, and the legacy Short/Full
          detail internally — unchanged data flow, only its placement
          changes here. */}
      <section className="workspace-panel workspace-forecast-panel" aria-label="AI прогноз">
        <AiAnalysisSection
          ticker={ticker}
          currentPrice={state.status === "loaded" ? state.data.price : null}
          onInsightSaved={() => setHistoryRefreshKey((key) => key + 1)}
        />
      </section>

      {/* INTELLIGENCE ROW — News Intelligence, full width, natural
          document flow (task scope §14: no forced tall column next to
          a much-shorter neighbor now that Forecast has its own row
          above). */}
      <section className="workspace-panel workspace-news-panel" aria-label="Новости">
        <InstrumentNewsSection ticker={ticker} />
      </section>

      {/* HISTORY — remains reachable without dominating the initial
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
  const freshness = formatFreshness(data.as_of);

  return (
    <header className="instrument-header">
      <div className="instrument-header-primary">
        <h1 className="instrument-ticker">{data.ticker}</h1>
        <div className="instrument-price-block">
          <span className="instrument-price">{price ?? UNAVAILABLE}</span>
          {change ? (
            <span
              className={`instrument-change instrument-change-${change.direction}`}
              aria-label={
                change.direction === "up" ? "рост" : change.direction === "down" ? "падение" : "без изменений"
              }
            >
              {change.text}
            </span>
          ) : (
            <span className="instrument-change-unavailable">{UNAVAILABLE}</span>
          )}
        </div>
      </div>
      <div className="instrument-header-meta">
        <span
          className={freshness.stale ? "instrument-freshness instrument-freshness-stale" : "instrument-freshness"}
          title={formatAsOf(data.as_of)}
        >
          {freshness.stale && <span className="instrument-freshness-dot" aria-hidden="true" />}
          {freshness.label}
        </span>
        <span>Источник: {formatSource(data.source)}</span>
      </div>
    </header>
  );
}
