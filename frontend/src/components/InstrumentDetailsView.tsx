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

export default function InstrumentDetailsView({ ticker }: { ticker: string }) {
  const [state, setState] = useState<ViewState>({ status: "loading" });

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
    <main className="instrument-details">
      <Link href="/" className="instrument-back-link">
        ← Назад к watchlist
      </Link>

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

        {state.status === "loaded" && <InstrumentDetailsContent data={state.data} />}
      </div>

      {/* Independent of the summary's own loading/error state above —
          a chart failure never hides an already-loaded summary, and a
          summary failure never blocks the chart (task scope §9/§13). */}
      <PriceChartSection ticker={ticker} />

      {/* Same independence rule applies to news: summary, chart, and
          news each own their loading/error state — no shared
          page-level state, no section's failure hides another's
          already-loaded data (task scope §9). */}
      <InstrumentNewsSection ticker={ticker} />

      <p className="instrument-disclaimer">
        Рыночные данные — только для просмотра и могут запаздывать; это не торговое исполнение и
        не рекомендация.
      </p>
    </main>
  );
}

function InstrumentDetailsContent({ data }: { data: InstrumentDetails }) {
  const price = formatPrice(data.price);
  const change = formatChange(data.change, data.change_percent);

  const stats: Array<{ label: string; value: string | null }> = [
    { label: "Open", value: formatPrice(data.open) },
    { label: "High", value: formatPrice(data.high) },
    { label: "Low", value: formatPrice(data.low) },
    { label: "Previous close", value: formatPrice(data.previous_close) },
    { label: "Volume", value: formatVolume(data.volume) },
  ];

  return (
    <>
      <header className="instrument-header">
        <h1 className="instrument-ticker">{data.ticker}</h1>
        <p className="instrument-price">{price ?? UNAVAILABLE}</p>
        {change ? (
          <p
            className={`instrument-change instrument-change-${change.direction}`}
            aria-label={
              change.direction === "up"
                ? "рост"
                : change.direction === "down"
                  ? "падение"
                  : "без изменений"
            }
          >
            {change.text}
          </p>
        ) : (
          <p className="instrument-change-unavailable">{UNAVAILABLE}</p>
        )}
      </header>

      <dl className="instrument-stats-grid">
        {stats.map((stat) => (
          <div className="instrument-stat" key={stat.label}>
            <dt className="instrument-stat-label">{stat.label}</dt>
            <dd className="instrument-stat-value">{stat.value ?? UNAVAILABLE}</dd>
          </div>
        ))}
        <div className="instrument-stat">
          <dt className="instrument-stat-label">Updated</dt>
          <dd className="instrument-stat-value">{formatAsOf(data.as_of)}</dd>
        </div>
        <div className="instrument-stat">
          <dt className="instrument-stat-label">Source</dt>
          <dd className="instrument-stat-value">{formatSource(data.source)}</dd>
        </div>
      </dl>
    </>
  );
}
