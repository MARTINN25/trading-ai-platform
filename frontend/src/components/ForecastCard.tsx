"use client";

import type {
  AnalysisHorizon,
  DirectionalView,
  ForecastState,
  InstrumentConfidenceLevel,
} from "@/lib/instrument-api";

/**
 * Phase 2B (Forecast Contract, FR-061/FR-062) — structurally satisfied
 * by both `InstrumentAiAnalysis` (fresh generation) and `InsightDetail`
 * (saved insight), same pattern as `InsightSections.tsx`'s
 * `InsightSectionsData`. The parent only renders this component once
 * it has already confirmed `horizon !== null` (task scope §17: old,
 * pre-Phase-2B insights simply never render this block at all).
 */
export interface ForecastCardData {
  horizon: AnalysisHorizon;
  forecast_state: ForecastState;
  directional_view: DirectionalView | null;
  confidence: InstrumentConfidenceLevel;
  concise_verdict: string;
  base_case: string | null;
  bullish_case: string | null;
  bearish_case: string | null;
  catalysts: string[];
  invalidation_conditions: string[];
  what_to_watch_next: string[];
  data_freshness: string;
  check_after: string | null;
  uncertainty: string | null;
  context_categories_used: string[];
}

export const HORIZON_LABELS: Record<AnalysisHorizon, string> = {
  short: "SHORT",
  medium: "MEDIUM",
  long: "LONG",
};

const HORIZON_HINTS: Record<AnalysisHorizon, string> = {
  short: "1–5 торговых дней",
  medium: "1–8 недель",
  long: "2–12 месяцев",
};

const CONFIDENCE_LABELS: Record<InstrumentConfidenceLevel, string> = {
  high: "высокая",
  medium: "средняя",
  low: "низкая",
};

export const DIRECTIONAL_LABELS: Record<DirectionalView, string> = {
  strongly_bullish: "Сильно бычий",
  bullish: "Умеренно бычий",
  neutral: "Нейтральный",
  bearish: "Умеренно медвежий",
  strongly_bearish: "Сильно медвежий",
};

const DIRECTIONAL_CLASS: Record<DirectionalView, string> = {
  strongly_bullish: "forecast-directional--strongly-bullish",
  bullish: "forecast-directional--bullish",
  neutral: "forecast-directional--neutral",
  bearish: "forecast-directional--bearish",
  strongly_bearish: "forecast-directional--strongly-bearish",
};

export const FORECAST_STATE_LABELS: Record<Exclude<ForecastState, "forecast">, string> = {
  no_quality_setup: "Нет качественной возможности",
  insufficient_edge: "Недостаточно перевеса для вывода",
  insufficient_data: "Недостаточно данных",
};

const FORECAST_STATE_EXPLANATIONS: Record<Exclude<ForecastState, "forecast">, string> = {
  no_quality_setup:
    "Ассистент не формирует бычий или медвежий вывод только потому, что был запрошен анализ — сейчас нет структурного основания для направленного прогноза.",
  insufficient_edge:
    "Сигналы противоречат друг другу без явного преобладания — направленный вывод был бы натянутым.",
  insufficient_data:
    "Собранных данных недостаточно, чтобы честно поддержать выбранный горизонт анализа.",
};

function formatCheckAfter(value: string | null): string {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium" }).format(date);
}

export default function ForecastCard({ data }: { data: ForecastCardData }) {
  const isNoEdge = data.forecast_state !== "forecast";

  return (
    <section className="forecast-card" aria-labelledby="forecast-card-heading">
      <h3 id="forecast-card-heading" className="forecast-card-heading">
        AI прогноз
      </h3>

      <div className="forecast-pills">
        <span className="forecast-pill forecast-pill--horizon" title={HORIZON_HINTS[data.horizon]}>
          {HORIZON_LABELS[data.horizon]} · {HORIZON_HINTS[data.horizon]}
        </span>
        <span className="forecast-pill">Уверенность: {CONFIDENCE_LABELS[data.confidence]}</span>
      </div>

      {isNoEdge ? (
        <div className="forecast-no-edge" role="status">
          <p className="forecast-no-edge-title">
            {FORECAST_STATE_LABELS[data.forecast_state as Exclude<ForecastState, "forecast">]}
          </p>
          <p className="forecast-no-edge-explanation">
            {FORECAST_STATE_EXPLANATIONS[data.forecast_state as Exclude<ForecastState, "forecast">]}
          </p>
          <p className="forecast-concise-verdict">{data.concise_verdict}</p>
        </div>
      ) : (
        <>
          {data.directional_view && (
            <p className={`forecast-directional ${DIRECTIONAL_CLASS[data.directional_view]}`}>
              {DIRECTIONAL_LABELS[data.directional_view]}
            </p>
          )}
          <p className="forecast-concise-verdict">{data.concise_verdict}</p>

          {data.base_case && (
            <div className="forecast-block">
              <h4>Основной сценарий</h4>
              <p>{data.base_case}</p>
            </div>
          )}
          {data.bullish_case && (
            <div className="forecast-block">
              <h4>Бычий сценарий</h4>
              <p>{data.bullish_case}</p>
            </div>
          )}
          {data.bearish_case && (
            <div className="forecast-block">
              <h4>Медвежий сценарий</h4>
              <p>{data.bearish_case}</p>
            </div>
          )}
          {data.catalysts.length > 0 && (
            <div className="forecast-block">
              <h4>Что поддерживает вывод</h4>
              <ul>
                {data.catalysts.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          {data.invalidation_conditions.length > 0 && (
            <div className="forecast-block">
              <h4>Что отменит гипотезу</h4>
              <ul>
                {data.invalidation_conditions.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          {data.what_to_watch_next.length > 0 && (
            <div className="forecast-block">
              <h4>Что отслеживать</h4>
              <ul>
                {data.what_to_watch_next.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}

      {data.uncertainty && (
        <p className="forecast-uncertainty">
          <span className="forecast-field-label">Неопределённость: </span>
          {data.uncertainty}
        </p>
      )}

      <p className="forecast-meta">
        {data.data_freshness}
        {data.check_after && <> · Повторная проверка не раньше: {formatCheckAfter(data.check_after)}</>}
        {data.context_categories_used.length > 0 && (
          <> · Учтено: {data.context_categories_used.join(", ")}</>
        )}
      </p>
    </section>
  );
}
