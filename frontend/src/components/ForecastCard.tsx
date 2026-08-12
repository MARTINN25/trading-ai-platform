"use client";

import type {
  AnalysisHorizon,
  DirectionalView,
  ForecastState,
  InstrumentConfidenceLevel,
  InstrumentKeyFact,
} from "@/lib/instrument-api";

/**
 * Phase 2B (Forecast Contract, FR-061/FR-062) — structurally satisfied
 * by both `InstrumentAiAnalysis` (fresh generation) and `InsightDetail`
 * (saved insight), same pattern as `InsightSections.tsx`'s
 * `InsightSectionsData`. The parent only renders this component once
 * it has already confirmed `horizon !== null` (task scope §17: old,
 * pre-Phase-2B insights simply never render this block at all).
 *
 * Phase 2B.1 (Professional Instrument Workspace) redesign (task scope
 * §10-§12): summary-first (horizon/state/direction/confidence/verdict
 * immediately visible, no scrolling through prose first), a compact
 * "decision context" strip, three sibling scenario cards, and a
 * scannable evidence/invalidation/watch-next grid. `key_facts`/
 * `key_drivers` are newly surfaced here (previously only shown in the
 * legacy FR-018 detail) as a short, capped "why this view" preview —
 * the full, untruncated list still lives in the legacy Short/Full
 * detail area (`InsightSections.tsx`), so nothing is deleted, only
 * also summarized here (task scope §12-§13: preview vs. full detail,
 * not the same paragraph repeated twice).
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
  key_facts: InstrumentKeyFact[];
  key_drivers: string[];
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

export const DIRECTIONAL_CLASS: Record<DirectionalView, string> = {
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

function formatDate(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium" }).format(date);
}

function formatPriceValue(value: string | null | undefined): string | null {
  if (!value) return null;
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  return num.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength).trimEnd()}…`;
}

const EVIDENCE_PREVIEW_LIMIT = 4;

export default function ForecastCard({
  data,
  currentPrice,
}: {
  data: ForecastCardData;
  /** Real, already-fetched current quote price (task scope §10's
   * "CURRENT" decision-strip item) — omitted (not fabricated) when the
   * caller has no live quote at hand (e.g. viewing a saved insight
   * from history, where "current" would conflate today's price with a
   * past forecast). */
  currentPrice?: string | null;
}) {
  const isNoEdge = data.forecast_state !== "forecast";
  const formattedCurrentPrice = formatPriceValue(currentPrice);
  const firstInvalidation = data.invalidation_conditions[0] ?? null;
  const watchItems = [...data.catalysts, ...data.what_to_watch_next].filter(
    (item, index, all) => all.indexOf(item) === index
  );
  const evidenceItems = [
    ...data.key_facts.map((fact) => fact.fact),
    ...data.key_drivers,
  ].filter((item, index, all) => all.indexOf(item) === index);

  return (
    <section className="forecast-card" aria-labelledby="forecast-card-heading">
      <div className="forecast-card-top">
        <h3 id="forecast-card-heading" className="forecast-card-heading">
          AI прогноз
        </h3>
        <div className="forecast-pills">
          <span className="forecast-pill forecast-pill--horizon" title={HORIZON_HINTS[data.horizon]}>
            {HORIZON_LABELS[data.horizon]} · {HORIZON_HINTS[data.horizon]}
          </span>
          <span className={`ai-analysis-confidence-badge ai-analysis-confidence-${data.confidence}`}>
            Уверенность: {CONFIDENCE_LABELS[data.confidence]}
          </span>
        </div>
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
        </>
      )}

      {/* Decision-context strip (task scope §10) — every value below
          already exists in deterministic evidence or forecast fields;
          "Наблюдаемый уровень" is an honest truncated preview of the
          model's own first invalidation condition (which the prompt
          requires to cite a real observed price/level), never an
          invented support/resistance number. */}
      <div className="forecast-decision-strip">
        <div className="forecast-decision-item">
          <span className="forecast-decision-label">Текущая цена</span>
          <span className="forecast-decision-value">{formattedCurrentPrice ?? "—"}</span>
        </div>
        <div className="forecast-decision-item">
          <span className="forecast-decision-label">Наблюдаемый уровень</span>
          <span className="forecast-decision-value forecast-decision-value--text">
            {firstInvalidation ? truncate(firstInvalidation, 58) : "—"}
          </span>
        </div>
        <div className="forecast-decision-item">
          <span className="forecast-decision-label">Инвалидация</span>
          <span className="forecast-decision-value">
            {data.invalidation_conditions.length > 0
              ? `${data.invalidation_conditions.length} усл.`
              : "—"}
          </span>
        </div>
        <div className="forecast-decision-item">
          <span className="forecast-decision-label">Проверка не раньше</span>
          <span className="forecast-decision-value">{formatDate(data.check_after) || "—"}</span>
        </div>
      </div>

      {!isNoEdge && (data.base_case || data.bullish_case || data.bearish_case) && (
        <div className="forecast-scenarios">
          {data.base_case && (
            <div className="forecast-scenario-card forecast-scenario-card--base">
              <h4>Основной сценарий</h4>
              <p>{data.base_case}</p>
            </div>
          )}
          {data.bullish_case && (
            <div className="forecast-scenario-card forecast-scenario-card--bull">
              <h4>Бычий сценарий</h4>
              <p>{data.bullish_case}</p>
            </div>
          )}
          {data.bearish_case && (
            <div className="forecast-scenario-card forecast-scenario-card--bear">
              <h4>Медвежий сценарий</h4>
              <p>{data.bearish_case}</p>
            </div>
          )}
        </div>
      )}

      {(evidenceItems.length > 0 || data.invalidation_conditions.length > 0 || watchItems.length > 0) && (
        <div className="forecast-evidence-grid">
          <div className="forecast-evidence-column">
            <h4>Почему такой вывод</h4>
            {evidenceItems.length > 0 ? (
              <ul>
                {evidenceItems.slice(0, EVIDENCE_PREVIEW_LIMIT).map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            ) : (
              <p className="forecast-evidence-empty">См. «Подробно» ниже.</p>
            )}
          </div>
          <div className="forecast-evidence-column">
            <h4>Что отменит гипотезу</h4>
            {data.invalidation_conditions.length > 0 ? (
              <ul>
                {data.invalidation_conditions.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            ) : (
              <p className="forecast-evidence-empty">Не указано.</p>
            )}
          </div>
          <div className="forecast-evidence-column">
            <h4>Что отслеживать</h4>
            {watchItems.length > 0 ? (
              <ul>
                {watchItems.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            ) : (
              <p className="forecast-evidence-empty">Не указано.</p>
            )}
          </div>
        </div>
      )}

      {data.uncertainty && (
        <p className="forecast-uncertainty">
          <span className="forecast-field-label">Неопределённость: </span>
          {data.uncertainty}
        </p>
      )}

      <p className="forecast-meta">
        {data.data_freshness}
        {data.context_categories_used.length > 0 && (
          <> · Учтено: {data.context_categories_used.join(", ")}</>
        )}
      </p>
    </section>
  );
}
