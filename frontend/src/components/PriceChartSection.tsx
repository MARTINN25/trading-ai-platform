"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getInstrumentPriceHistory,
  InstrumentApiError,
  type InstrumentHistoryPeriod,
  type InstrumentPriceHistory,
} from "@/lib/instrument-api";
import PriceChart from "@/components/PriceChart";

type PeriodState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "loaded"; data: InstrumentPriceHistory }
  | { status: "error"; message: string };

const PERIODS: InstrumentHistoryPeriod[] = ["1D", "5D", "1M"];
const PERIOD_LABELS: Record<InstrumentHistoryPeriod, string> = {
  "1D": "1Д",
  "5D": "5Д",
  "1M": "1М",
};
// Task scope §9: "default period — один разумный период, например 1D".
const DEFAULT_PERIOD: InstrumentHistoryPeriod = "1D";

const timeOnlyFormatter = new Intl.DateTimeFormat("ru-RU", { timeStyle: "short" });
const dateTimeFormatter = new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeStyle: "short" });
const dateOnlyFormatter = new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium" });

function formatTimestamp(value: string, period: InstrumentHistoryPeriod): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  if (period === "1D") return timeOnlyFormatter.format(date);
  if (period === "1M") return dateOnlyFormatter.format(date);
  return dateTimeFormatter.format(date);
}

function formatClose(value: string): string | null {
  const num = Number(value);
  if (!Number.isFinite(num)) {
    return null;
  }
  return `$${num.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function initialStates(): Record<InstrumentHistoryPeriod, PeriodState> {
  return { "1D": { status: "idle" }, "5D": { status: "idle" }, "1M": { status: "idle" } };
}

export default function PriceChartSection({ ticker }: { ticker: string }) {
  const [activePeriod, setActivePeriod] = useState<InstrumentHistoryPeriod>(DEFAULT_PERIOD);
  const [statesByPeriod, setStatesByPeriod] =
    useState<Record<InstrumentHistoryPeriod, PeriodState>>(initialStates);

  const load = useCallback(
    (period: InstrumentHistoryPeriod) => {
      setStatesByPeriod((prev) => ({ ...prev, [period]: { status: "loading" } }));
      getInstrumentPriceHistory(ticker, period)
        .then((data) => {
          setStatesByPeriod((prev) => ({ ...prev, [period]: { status: "loaded", data } }));
        })
        .catch((error: unknown) => {
          const message =
            error instanceof InstrumentApiError ? error.message : "Не удалось загрузить график.";
          setStatesByPeriod((prev) => ({ ...prev, [period]: { status: "error", message } }));
        });
    },
    [ticker]
  );

  useEffect(() => {
    // Only the default period loads on page open (task scope §6) — the
    // other two load only when their button is clicked, below.
    setActivePeriod(DEFAULT_PERIOD);
    setStatesByPeriod(initialStates());
    load(DEFAULT_PERIOD);
  }, [ticker, load]);

  function handlePeriodClick(period: InstrumentHistoryPeriod): void {
    setActivePeriod(period);
    const state = statesByPeriod[period];
    // Already loaded (or currently loading) periods are never
    // re-fetched on re-click — one request per period per page visit,
    // not one per click (task scope §6).
    if (state.status === "idle" || state.status === "error") {
      load(period);
    }
  }

  const currentState = statesByPeriod[activePeriod];

  return (
    <section className="price-chart-section" aria-labelledby="price-chart-heading">
      <h2 id="price-chart-heading">График цены</h2>

      <div className="price-chart-periods" role="group" aria-label="Период графика">
        {PERIODS.map((period) => (
          <button
            key={period}
            type="button"
            className="price-chart-period-button"
            aria-pressed={period === activePeriod}
            onClick={() => handlePeriodClick(period)}
          >
            {PERIOD_LABELS[period]}
          </button>
        ))}
      </div>

      <div aria-live="polite">
        {(currentState.status === "idle" || currentState.status === "loading") && (
          <p className="price-chart-loading">Загрузка графика…</p>
        )}

        {currentState.status === "error" && (
          <div className="price-chart-error" role="alert">
            <p>{currentState.message}</p>
            <button type="button" onClick={() => load(activePeriod)}>
              Повторить
            </button>
          </div>
        )}

        {currentState.status === "loaded" && currentState.data.points.length === 0 && (
          <p className="price-chart-empty">Нет данных за выбранный период.</p>
        )}

        {currentState.status === "loaded" && currentState.data.points.length > 0 && (
          <>
            <div className="price-chart-container">
              <PriceChart points={currentState.data.points} />
            </div>
            <p className="price-chart-summary">
              Последняя цена:{" "}
              {formatClose(currentState.data.points[currentState.data.points.length - 1].close) ??
                "Данные недоступны"}{" "}
              · Период: {PERIOD_LABELS[activePeriod]} · Обновлено:{" "}
              {formatTimestamp(
                currentState.data.points[currentState.data.points.length - 1].timestamp,
                activePeriod
              )}
            </p>
          </>
        )}
      </div>
    </section>
  );
}
