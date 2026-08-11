"use client";

import type { InstrumentConfidenceLevel, InstrumentKeyFact } from "@/lib/instrument-api";

/**
 * FR-021/FR-022 — short/full is a **presentation-only** toggle over an
 * already-fully-received structured result (`ADR-0003-frontend-stack.md`
 * §23 explicitly classifies it as local UI state, not URL/server
 * state). No new LLM call, no new endpoint, no data is ever deleted or
 * regenerated — only visibility of already-fetched fields changes.
 *
 * Shared by `AiAnalysisSection.tsx` (current generation) and
 * `InsightHistorySection.tsx` (saved insight) so both surfaces support
 * the same short/full semantics identically (task scope §7) — this is
 * a small, purpose-built component for one specific structured shape,
 * not a generic rendering framework.
 */
export type InsightViewMode = "short" | "full";

/** The 10 FR-018 content fields, structurally satisfied by both
 * `InstrumentAiAnalysis` and `InsightDetail` (extra fields on either —
 * `analysis_token`, `id`, `provider`, etc. — are simply ignored here). */
export interface InsightSectionsData {
  summary: string;
  key_facts: InstrumentKeyFact[];
  price_context: string;
  news_context: string;
  insight_hypothesis: string;
  confidence: InstrumentConfidenceLevel;
  confidence_reason: string;
  considerations: string[];
  risks: string[];
  key_drivers: string[];
  data_freshness: string;
}

const CONFIDENCE_LABELS: Record<InstrumentConfidenceLevel, string> = {
  high: "Высокая",
  medium: "Средняя",
  low: "Низкая",
};

/**
 * Product Owner decision (сбалансированный состав, вариант B): краткий
 * режим показывает разделы 1 (Краткое резюме), 2 (Ключевые факты), 5
 * (Уровень уверенности), 6 (Что можно рассмотреть), 7 (Основные
 * риски) — ровно те же поля, что и в полном режиме, без обрезки
 * текста внутри раздела (никакой клиентской/серверной суммаризации).
 * Разделы 3 (Анализ), 4 (Инсайт/гипотеза), 8 (Key drivers), 9
 * (Актуальность данных) — только в полном режиме. По умолчанию —
 * «Кратко» (тоже Product Owner decision).
 */
export function ModeToggle({
  mode,
  onChange,
}: {
  mode: InsightViewMode;
  onChange: (mode: InsightViewMode) => void;
}) {
  return (
    <div className="insight-mode-toggle" role="group" aria-label="Режим отображения инсайта">
      <button
        type="button"
        aria-pressed={mode === "short"}
        className={mode === "short" ? "insight-mode-button-selected" : "insight-mode-button"}
        onClick={() => onChange("short")}
      >
        Кратко
      </button>
      <button
        type="button"
        aria-pressed={mode === "full"}
        className={mode === "full" ? "insight-mode-button-selected" : "insight-mode-button"}
        onClick={() => onChange("full")}
      >
        Подробно
      </button>
    </div>
  );
}

export default function InsightSections({ data, mode }: { data: InsightSectionsData; mode: InsightViewMode }) {
  return (
    <>
      <div className="ai-analysis-block">
        <h3>Краткий вывод</h3>
        <p>{data.summary}</p>
      </div>

      <div className="ai-analysis-block">
        <h3>Ключевые факты</h3>
        <ul className="ai-analysis-key-facts">
          {data.key_facts.map((fact, index) => (
            <li key={index}>
              <span className="ai-analysis-key-fact-text">{fact.fact}</span>
              <span className="ai-analysis-key-fact-source">{fact.source}</span>
            </li>
          ))}
        </ul>
      </div>

      {mode === "full" && (
        <div className="ai-analysis-block">
          <h3>Анализ</h3>
          <p>{data.price_context}</p>
          <p>{data.news_context}</p>
        </div>
      )}

      {mode === "full" && (
        <div className="ai-analysis-block">
          <h3>Инсайт / гипотеза</h3>
          <p>{data.insight_hypothesis}</p>
        </div>
      )}

      <div className="ai-analysis-block">
        <h3>Уровень уверенности</h3>
        <p className="ai-analysis-confidence">
          <span className={`ai-analysis-confidence-badge ai-analysis-confidence-${data.confidence}`}>
            {CONFIDENCE_LABELS[data.confidence]}
          </span>
        </p>
        <p>{data.confidence_reason}</p>
      </div>

      <div className="ai-analysis-block">
        <h3>Что можно рассмотреть</h3>
        <ul>
          {data.considerations.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
      </div>

      <div className="ai-analysis-block">
        <h3>Риски</h3>
        <ul className="ai-analysis-risks">
          {data.risks.map((risk, index) => (
            <li key={index}>{risk}</li>
          ))}
        </ul>
      </div>

      {mode === "full" && (
        <div className="ai-analysis-block">
          <h3>Что сильнее всего повлияло на вывод</h3>
          <ul>
            {data.key_drivers.map((driver, index) => (
              <li key={index}>{driver}</li>
            ))}
          </ul>
        </div>
      )}

      {mode === "full" && (
        <div className="ai-analysis-block">
          <h3>Актуальность данных</h3>
          <p>{data.data_freshness}</p>
        </div>
      )}
    </>
  );
}
