"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getInsightDetail,
  getInstrumentInsights,
  InstrumentApiError,
  type InsightDetail,
  type InsightSummary,
  type InstrumentConfidenceLevel,
} from "@/lib/instrument-api";

type HistoryState =
  | { status: "loading" }
  | { status: "loaded"; items: InsightSummary[] }
  | { status: "error"; message: string };

type DetailState =
  | { status: "loading" }
  | { status: "loaded"; data: InsightDetail }
  | { status: "error"; message: string };

const timestampFormatter = new Intl.DateTimeFormat("ru-RU", {
  dateStyle: "medium",
  timeStyle: "short",
});

function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return timestampFormatter.format(date);
}

const CONFIDENCE_LABELS: Record<InstrumentConfidenceLevel, string> = {
  high: "Высокая",
  medium: "Средняя",
  low: "Низкая",
};

export default function InsightHistorySection({
  ticker,
  refreshKey,
}: {
  ticker: string;
  /** Bumped by the parent (see `InstrumentDetailsView.tsx`) right after
   * a successful save in `AiAnalysisSection` — the only bridge between
   * these two otherwise-independent sections. */
  refreshKey: number;
}) {
  const [state, setState] = useState<HistoryState>({ status: "loading" });
  // Expandable per-item detail — fetched lazily on "Открыть", not
  // embedded in the (compact) list response (task scope §14).
  const [expanded, setExpanded] = useState<Record<number, DetailState>>({});

  const load = useCallback(() => {
    setState({ status: "loading" });
    setExpanded({});
    getInstrumentInsights(ticker)
      .then((data) => setState({ status: "loaded", items: data.items }))
      .catch((error: unknown) => {
        const message =
          error instanceof InstrumentApiError ? error.message : "История AI-анализов недоступна.";
        setState({ status: "error", message });
      });
  }, [ticker]);

  useEffect(() => {
    // Loads on mount and again whenever `refreshKey` changes (a save
    // just happened) — no polling, no timer (task scope §14, §16).
    load();
  }, [load, refreshKey]);

  function toggleExpand(id: number): void {
    if (expanded[id]) {
      setExpanded((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      return;
    }
    setExpanded((prev) => ({ ...prev, [id]: { status: "loading" } }));
    getInsightDetail(id)
      .then((data) => setExpanded((prev) => ({ ...prev, [id]: { status: "loaded", data } })))
      .catch((error: unknown) => {
        const message =
          error instanceof InstrumentApiError ? error.message : "Не удалось загрузить инсайт.";
        setExpanded((prev) => ({ ...prev, [id]: { status: "error", message } }));
      });
  }

  return (
    <section className="insight-history-section" aria-labelledby="insight-history-heading">
      <h2 id="insight-history-heading">История AI-анализов</h2>

      <div aria-live="polite">
        {state.status === "loading" && (
          <p className="insight-history-loading">Загрузка истории…</p>
        )}

        {state.status === "error" && (
          <div className="insight-history-error" role="alert">
            <p>{state.message}</p>
            <button type="button" onClick={load}>
              Повторить
            </button>
          </div>
        )}

        {state.status === "loaded" && state.items.length === 0 && (
          <p className="insight-history-empty">
            Сохранённых AI-анализов пока нет. Сгенерируйте анализ выше и нажмите «Сохранить
            инсайт».
          </p>
        )}

        {state.status === "loaded" && state.items.length > 0 && (
          // Bounded, backend-capped list — no infinite scroll (task scope §14).
          <ul className="insight-history-list">
            {state.items.map((item) => {
              const detail = expanded[item.id];
              return (
                <li key={item.id} className="insight-history-item">
                  <p className="insight-history-item-meta">
                    {formatTimestamp(item.created_at)} · Confidence:{" "}
                    <span
                      className={`insight-history-confidence insight-history-confidence-${item.confidence}`}
                    >
                      {CONFIDENCE_LABELS[item.confidence]}
                    </span>
                  </p>
                  <p className="insight-history-item-summary">{item.summary}</p>
                  <button type="button" onClick={() => toggleExpand(item.id)}>
                    {detail ? "Скрыть" : "Открыть"}
                  </button>

                  {detail && detail.status === "loading" && (
                    <p className="insight-history-detail-loading">Загрузка…</p>
                  )}

                  {detail && detail.status === "error" && (
                    <div className="insight-history-detail-error" role="alert">
                      <p>{detail.message}</p>
                    </div>
                  )}

                  {detail && detail.status === "loaded" && (
                    <div className="insight-history-detail">
                      <p>
                        <strong>Ключевые факты:</strong>
                      </p>
                      <ul>
                        {detail.data.key_facts.map((fact, index) => (
                          <li key={index}>
                            {fact.fact} <em>({fact.source})</em>
                          </li>
                        ))}
                      </ul>
                      <p>
                        <strong>Инсайт / гипотеза:</strong> {detail.data.insight_hypothesis}
                      </p>
                      <p>
                        <strong>Обоснование уверенности:</strong> {detail.data.confidence_reason}
                      </p>
                      <p>
                        <strong>Что можно рассмотреть:</strong>
                      </p>
                      <ul>
                        {detail.data.considerations.map((item, index) => (
                          <li key={index}>{item}</li>
                        ))}
                      </ul>
                      <p>
                        <strong>Риски:</strong>
                      </p>
                      <ul>
                        {detail.data.risks.map((risk, index) => (
                          <li key={index}>{risk}</li>
                        ))}
                      </ul>
                      <p>
                        <strong>Что сильнее всего повлияло на вывод:</strong>
                      </p>
                      <ul>
                        {detail.data.key_drivers.map((driver, index) => (
                          <li key={index}>{driver}</li>
                        ))}
                      </ul>
                      <p>
                        <strong>Актуальность данных:</strong> {detail.data.data_freshness}
                      </p>
                      <p className="insight-history-detail-provenance">
                        {detail.data.provider} / {detail.data.model} · prompt{" "}
                        {detail.data.prompt_version} · schema {detail.data.schema_version}
                      </p>
                      <p className="insight-history-detail-disclaimer">{detail.data.disclaimer}</p>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
