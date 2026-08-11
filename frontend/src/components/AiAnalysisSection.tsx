"use client";

import { useState } from "react";
import {
  generateInstrumentAnalysis,
  saveInsight,
  InstrumentApiError,
  type InstrumentAiAnalysis,
  type InstrumentConfidenceLevel,
} from "@/lib/instrument-api";

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

const CONFIDENCE_LABELS: Record<InstrumentConfidenceLevel, string> = {
  high: "Высокая",
  medium: "Средняя",
  low: "Низкая",
};

export default function AiAnalysisSection({
  ticker,
  onInsightSaved,
}: {
  ticker: string;
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

  function generate(): void {
    setState({ status: "loading" });
    setSaveState({ status: "idle" });
    generateInstrumentAnalysis(ticker)
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
      <h2 id="ai-analysis-heading">AI-анализ</h2>

      <div aria-live="polite">
        {state.status === "idle" && (
          <div className="ai-analysis-idle">
            <p>AI-анализ ещё не запущен.</p>
            <button type="button" onClick={generate} disabled={isLoading}>
              Сгенерировать AI-анализ
            </button>
          </div>
        )}

        {state.status === "loading" && (
          <p className="ai-analysis-loading">Генерация AI-анализа…</p>
        )}

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
            <div className="ai-analysis-block">
              <h3>Краткий вывод</h3>
              {/* Plain text children only — React escapes automatically.
                  Never dangerouslySetInnerHTML, never a Markdown-to-HTML
                  renderer (task scope §17). */}
              <p>{state.data.summary}</p>
            </div>

            <div className="ai-analysis-block">
              <h3>Ключевые факты</h3>
              <ul className="ai-analysis-key-facts">
                {state.data.key_facts.map((fact, index) => (
                  <li key={index}>
                    <span className="ai-analysis-key-fact-text">{fact.fact}</span>
                    <span className="ai-analysis-key-fact-source">{fact.source}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="ai-analysis-block">
              <h3>Анализ</h3>
              <p>{state.data.price_context}</p>
              <p>{state.data.news_context}</p>
            </div>

            <div className="ai-analysis-block">
              <h3>Инсайт / гипотеза</h3>
              <p>{state.data.insight_hypothesis}</p>
            </div>

            <div className="ai-analysis-block">
              <h3>Уровень уверенности</h3>
              <p className="ai-analysis-confidence">
                <span className={`ai-analysis-confidence-badge ai-analysis-confidence-${state.data.confidence}`}>
                  {CONFIDENCE_LABELS[state.data.confidence]}
                </span>
              </p>
              <p>{state.data.confidence_reason}</p>
            </div>

            <div className="ai-analysis-block">
              <h3>Что можно рассмотреть</h3>
              <ul>
                {state.data.considerations.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </div>

            <div className="ai-analysis-block">
              <h3>Риски</h3>
              <ul className="ai-analysis-risks">
                {state.data.risks.map((risk, index) => (
                  <li key={index}>{risk}</li>
                ))}
              </ul>
            </div>

            <div className="ai-analysis-block">
              <h3>Что сильнее всего повлияло на вывод</h3>
              <ul>
                {state.data.key_drivers.map((driver, index) => (
                  <li key={index}>{driver}</li>
                ))}
              </ul>
            </div>

            <div className="ai-analysis-block">
              <h3>Актуальность данных</h3>
              <p>{state.data.data_freshness}</p>
            </div>

            <p className="ai-analysis-meta">
              Сгенерировано: {formatGeneratedAt(state.data.generated_at)} · Источник анализа: AI
            </p>

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
          </div>
        )}
      </div>

      <p className="ai-analysis-disclaimer">{FIXED_DISCLAIMER}</p>
    </section>
  );
}
