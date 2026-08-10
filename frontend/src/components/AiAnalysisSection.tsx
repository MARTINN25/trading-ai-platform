"use client";

import { useState } from "react";
import {
  generateInstrumentAnalysis,
  InstrumentApiError,
  type InstrumentAiAnalysis,
} from "@/lib/instrument-api";

type AnalysisState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "loaded"; data: InstrumentAiAnalysis }
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

export default function AiAnalysisSection({ ticker }: { ticker: string }) {
  // Deliberately no useEffect anywhere in this component — generation
  // only ever starts from an explicit button click (task scope §11:
  // never on page load, F5, chart-period switch, or news load).
  const [state, setState] = useState<AnalysisState>({ status: "idle" });

  function generate(): void {
    setState({ status: "loading" });
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

  const isLoading = state.status === "loading";

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
              <h3>Контекст цены</h3>
              <p>{state.data.price_context}</p>
            </div>

            <div className="ai-analysis-block">
              <h3>Контекст новостей</h3>
              <p>{state.data.news_context}</p>
            </div>

            <div className="ai-analysis-block">
              <h3>Риски</h3>
              <ul className="ai-analysis-risks">
                {state.data.risks.map((risk, index) => (
                  <li key={index}>{risk}</li>
                ))}
              </ul>
            </div>

            <p className="ai-analysis-meta">
              Сгенерировано: {formatGeneratedAt(state.data.generated_at)} · Источник анализа: AI
            </p>

            <button type="button" onClick={generate} disabled={isLoading}>
              Обновить AI-анализ
            </button>
          </div>
        )}
      </div>

      <p className="ai-analysis-disclaimer">{FIXED_DISCLAIMER}</p>
    </section>
  );
}
