"use client";

import { useState } from "react";
import {
  generateInstrumentAnalysis,
  saveInsight,
  InstrumentApiError,
  type AnalysisHorizon,
  type InstrumentAiAnalysis,
} from "@/lib/instrument-api";
import InsightSections, { ModeToggle, type InsightViewMode } from "@/components/InsightSections";
import ForecastCard from "@/components/ForecastCard";
import HorizonSelector, { HORIZON_HINTS } from "@/components/HorizonSelector";

type AnalysisState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "loaded"; data: InstrumentAiAnalysis }
  | { status: "error"; message: string };

// Explicit save (Product Owner decision) — generation and persistence
// are decoupled. `saveState` is reset to "idle" on every new
// generation, since a fresh `analysis_token` makes any prior save
// state stale.
type SaveState =
  | { status: "idle" }
  | { status: "saving" }
  | { status: "saved"; insightId: number }
  | { status: "error"; message: string };

const generatedAtFormatter = new Intl.DateTimeFormat("ru-RU", {
  dateStyle: "medium",
  timeStyle: "short",
});

function formatGeneratedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return generatedAtFormatter.format(date);
}

const FIXED_DISCLAIMER =
  "AI-анализ носит информационный характер и не является инвестиционной рекомендацией.";

// Only categories the pipeline actually assembles today (task scope
// §7: "do not pretend unavailable contexts are implemented") — mirrors
// the real `context_categories_used` values a generated analysis
// returns (`identity`/`price`/`history`/`news`), phrased for a reader
// deciding whether to click "Сгенерировать", not as a technical list.
const IDLE_INPUTS = [
  "Цена и текущее движение",
  "История котировок за период",
  "Релевантные новости",
  "Доступный рыночный контекст",
];

/**
 * Structured loading state (task scope §17) — mirrors `ForecastCard`'s
 * own shape (pills, verdict line, decision strip, three scenario
 * placeholders) so the panel doesn't collapse to a single line of text
 * and doesn't cause a destructive layout jump when the real response
 * arrives. No fake token streaming — the backend returns one blocking
 * response, so this is a static structural placeholder with a subtle
 * pulse, not a simulated typing effect.
 */
function ForecastSkeleton({ horizon }: { horizon: AnalysisHorizon }) {
  return (
    <div className="forecast-skeleton" role="status" aria-live="polite">
      <div className="forecast-skeleton-pills">
        <span className="forecast-skeleton-pill forecast-skeleton-pill--wide" />
        <span className="forecast-skeleton-pill" />
      </div>
      <span className="forecast-skeleton-line forecast-skeleton-line--title" />
      <span className="forecast-skeleton-line forecast-skeleton-line--full" />
      <span className="forecast-skeleton-line forecast-skeleton-line--full" />
      <div className="forecast-skeleton-strip">
        <span className="forecast-skeleton-box" />
        <span className="forecast-skeleton-box" />
        <span className="forecast-skeleton-box" />
        <span className="forecast-skeleton-box" />
      </div>
      <div className="forecast-skeleton-scenarios">
        <span className="forecast-skeleton-card" />
        <span className="forecast-skeleton-card" />
        <span className="forecast-skeleton-card" />
      </div>
      <p className="forecast-skeleton-caption">
        Собираем рыночные данные и формируем прогноз на горизонте {HORIZON_HINTS[horizon]}…
      </p>
    </div>
  );
}

export default function AiAnalysisSection({
  ticker,
  currentPrice,
  onInsightSaved,
}: {
  ticker: string;
  /** Real, already-fetched quote price (task scope §10) — threaded
   * down to `ForecastCard`'s decision-context strip, never fabricated
   * here if the caller doesn't have one yet. */
  currentPrice?: string | null;
  /** Notifies the parent (see `InstrumentDetailsView.tsx`) so the
   * independent history section can refresh — sections stay decoupled,
   * this is the one explicit bridge between "just saved" and "history
   * should reload" (task scope §14-§16). */
  onInsightSaved?: () => void;
}) {
  // Deliberately no useEffect anywhere in this component — generation
  // only ever starts from an explicit button click (task scope §11:
  // never on page load, F5, chart-period switch, or news load).
  const [state, setState] = useState<AnalysisState>({ status: "idle" });
  const [saveState, setSaveState] = useState<SaveState>({ status: "idle" });
  // FR-021/022 — presentation-only, local UI state (`ADR-0003` §23),
  // no network request on change (task scope §8/§16). Product Owner
  // decision: default "Кратко"; resets to default on a fresh
  // generation, same as `saveState` above.
  const [mode, setMode] = useState<InsightViewMode>("short");
  // FR-006 — visibly selected and changeable before every generation
  // (task scope §19); a pre-selected value is not a silent backend
  // default — the user sees and can change it before clicking
  // "Сгенерировать", and the value actually sent is always this one,
  // never omitted. Preserved across generation (task scope §17) —
  // nothing here ever resets `horizon` itself.
  const [horizon, setHorizon] = useState<AnalysisHorizon>("short");

  function generate(): void {
    setState({ status: "loading" });
    setSaveState({ status: "idle" });
    setMode("short");
    generateInstrumentAnalysis(ticker, horizon)
      .then((data) => setState({ status: "loaded", data }))
      .catch((error: unknown) => {
        const message =
          error instanceof InstrumentApiError
            ? error.message
            : "Не удалось сгенерировать AI-анализ.";
        setState({ status: "error", message });
      });
  }

  function save(): void {
    if (state.status !== "loaded") {
      return;
    }
    const analysisToken = state.data.analysis_token;
    setSaveState({ status: "saving" });
    saveInsight(ticker, analysisToken)
      .then((insight) => {
        setSaveState({ status: "saved", insightId: insight.id });
        onInsightSaved?.();
      })
      .catch((error: unknown) => {
        const message =
          error instanceof InstrumentApiError ? error.message : "Не удалось сохранить инсайт.";
        setSaveState({ status: "error", message });
      });
  }

  const isLoading = state.status === "loading";
  const isSaving = saveState.status === "saving";

  return (
    <section className="ai-analysis-section" aria-labelledby="ai-analysis-heading">
      <h2 id="ai-analysis-heading">AI рыночный тезис</h2>

      <div aria-live="polite">
        <HorizonSelector horizon={horizon} onChange={setHorizon} disabled={isLoading} />

        {/* A purposeful "ready" state instead of a near-empty panel
            (task scope §7): states what the analysis will actually
            evaluate — real, already-implemented context categories
            only, never a roadmap promise. */}
        {state.status === "idle" && (
          <div className="ai-idle-panel">
            <p className="ai-idle-eyebrow">Анализ ещё не запущен</p>
            <p className="ai-idle-lead">
              Выберите горизонт выше и запустите генерацию, чтобы получить структурированный
              прогноз: направление, сценарии, уверенность и условия инвалидации.
            </p>
            <div className="ai-idle-inputs">
              <p className="ai-idle-inputs-title">Что учитывает анализ сейчас</p>
              <ul className="ai-idle-inputs-list">
                {IDLE_INPUTS.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
            <button type="button" className="ai-idle-generate" onClick={generate} disabled={isLoading}>
              Сгенерировать анализ
            </button>
          </div>
        )}

        {state.status === "loading" && <ForecastSkeleton horizon={horizon} />}

        {state.status === "error" && (
          <div className="ai-analysis-error" role="alert">
            <p>{state.message}</p>
            <button type="button" onClick={generate} disabled={isLoading}>
              Повторить
            </button>
          </div>
        )}

        {state.status === "loaded" && (
          <div className="ai-analysis-result">
            <ForecastCard data={state.data} currentPrice={currentPrice} />

            <div className="ai-analysis-actions">
              <button type="button" onClick={generate} disabled={isLoading}>
                Обновить AI-анализ
              </button>

              {saveState.status !== "saved" && (
                <button type="button" onClick={save} disabled={isSaving}>
                  {isSaving ? "Сохранение…" : "Сохранить инсайт"}
                </button>
              )}
            </div>

            <div aria-live="polite">
              {saveState.status === "saved" && (
                <p className="ai-analysis-save-confirmation">Сохранено в истории.</p>
              )}
              {saveState.status === "error" && (
                <div className="ai-analysis-save-error" role="alert">
                  <p>{saveState.message}</p>
                  <button type="button" onClick={save} disabled={isSaving}>
                    Повторить сохранение
                  </button>
                </div>
              )}
            </div>

            {/* Legacy FR-018 10-section structure — preserved in full,
                just visually secondary now (task scope §12-§13): a
                collapsed <details> below the forecast decision
                content, not deleted, not competing with it for
                attention. */}
            <details className="ai-analysis-detail">
              <summary>Подробный анализ (10 разделов FR-018)</summary>
              <div className="ai-analysis-detail-body">
                <ModeToggle mode={mode} onChange={setMode} />
                {/* Plain text children only throughout — React escapes
                    automatically. Never dangerouslySetInnerHTML, never a
                    Markdown-to-HTML renderer (task scope §17 of Phase 2B). */}
                <InsightSections data={state.data} mode={mode} />
                <p className="ai-analysis-meta">
                  Сгенерировано: {formatGeneratedAt(state.data.generated_at)} · Источник анализа: AI
                </p>
              </div>
            </details>
          </div>
        )}
      </div>

      <p className="ai-analysis-disclaimer">{FIXED_DISCLAIMER}</p>
    </section>
  );
}
