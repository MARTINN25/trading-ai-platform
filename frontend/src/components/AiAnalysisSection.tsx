"use client";

import { useState } from "react";
import {
  generateInstrumentAnalysis,
  saveInsight,
  InstrumentApiError,
  type InstrumentAiAnalysis,
} from "@/lib/instrument-api";
import InsightSections, { ModeToggle, type InsightViewMode } from "@/components/InsightSections";

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
  // FR-021/022 — presentation-only, local UI state (`ADR-0003` §23),
  // no network request on change (task scope §8/§16). Product Owner
  // decision: default "Кратко"; resets to default on a fresh
  // generation, same as `saveState` above.
  const [mode, setMode] = useState<InsightViewMode>("short");

  function generate(): void {
    setState({ status: "loading" });
    setSaveState({ status: "idle" });
    setMode("short");
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
            <ModeToggle mode={mode} onChange={setMode} />

            {/* Plain text children only throughout — React escapes
                automatically. Never dangerouslySetInnerHTML, never a
                Markdown-to-HTML renderer (task scope §17). */}
            <InsightSections data={state.data} mode={mode} />

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
