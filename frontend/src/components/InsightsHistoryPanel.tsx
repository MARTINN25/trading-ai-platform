"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  getInsightDetail,
  getRecentInsights,
  InstrumentApiError,
  type InsightDetail,
  type InsightSummary,
  type InstrumentConfidenceLevel,
} from "@/lib/instrument-api";
import InsightSections, { ModeToggle, type InsightViewMode } from "@/components/InsightSections";

/**
 * Cross-ticker Insights/History (Phase 1, task scope §8 —
 * `INFORMATION_ARCHITECTURE.md` §2.4). Reuses `InsightHistorySection`'s
 * rendering pattern (compact list → lazy detail → `InsightSections`/
 * `ModeToggle` short/full mode) rather than forking a large duplicated
 * renderer, but deliberately omits the per-instrument evaluation/
 * outcome forms (task scope §8 lists ticker/timestamp/confidence/
 * summary/detail/instrument-link only — evaluation stays where it
 * already lives, on the Instrument Workspace's own history section).
 */

type ListState =
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

export default function InsightsHistoryPanel({ openInsightId }: { openInsightId?: number }) {
  const [state, setState] = useState<ListState>({ status: "loading" });
  const [expanded, setExpanded] = useState<Record<number, DetailState>>({});
  const [modes, setModes] = useState<Record<number, InsightViewMode>>({});

  const load = useCallback(() => {
    setState({ status: "loading" });
    getRecentInsights()
      .then((data) => setState({ status: "loaded", items: data.items }))
      .catch((error: unknown) => {
        const message =
          error instanceof InstrumentApiError ? error.message : "История инсайтов недоступна.";
        setState({ status: "error", message });
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openDetail = useCallback((id: number) => {
    setExpanded((prev) => ({ ...prev, [id]: { status: "loading" } }));
    setModes((prev) => ({ ...prev, [id]: "short" }));
    getInsightDetail(id)
      .then((data) => setExpanded((prev) => ({ ...prev, [id]: { status: "loaded", data } })))
      .catch((error: unknown) => {
        const message =
          error instanceof InstrumentApiError ? error.message : "Не удалось загрузить инсайт.";
        setExpanded((prev) => ({ ...prev, [id]: { status: "error", message } }));
      });
  }, []);

  // Auto-open the insight linked from a journal entry ("Инсайт
  // #{id}" link, task scope §9) — independent of whether that insight
  // happens to be within the bounded recent list below.
  useEffect(() => {
    if (openInsightId !== undefined) {
      openDetail(openInsightId);
    }
  }, [openInsightId, openDetail]);

  function toggleExpand(id: number): void {
    if (expanded[id]) {
      setExpanded((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      setModes((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      return;
    }
    openDetail(id);
  }

  return (
    <main className="insights-page">
      <header className="insights-page-header">
        <h1>История инсайтов</h1>
        <p className="insights-page-subtitle">
          Все сохранённые AI-анализы по всем инструментам, от новых к старым.
        </p>
      </header>

      {openInsightId !== undefined && expanded[openInsightId] && (
        <section className="insights-list-item insights-list-item-highlighted">
          <p className="insights-list-item-meta">Открыт по ссылке из дневника: #{openInsightId}</p>
          {expanded[openInsightId].status === "loading" && (
            <p className="text-muted">Загрузка…</p>
          )}
          {expanded[openInsightId].status === "error" && (
            <p className="insights-list-error" role="alert">
              {(expanded[openInsightId] as { status: "error"; message: string }).message}
            </p>
          )}
          {expanded[openInsightId].status === "loaded" && (
            <InsightDetailBlock
              detail={(expanded[openInsightId] as { status: "loaded"; data: InsightDetail }).data}
              mode={modes[openInsightId] ?? "short"}
              onModeChange={(nextMode) =>
                setModes((prev) => ({ ...prev, [openInsightId]: nextMode }))
              }
            />
          )}
        </section>
      )}

      <div aria-live="polite">
        {state.status === "loading" && <p className="insights-list-loading">Загрузка истории…</p>}

        {state.status === "error" && (
          <div className="insights-list-error" role="alert">
            <p>{state.message}</p>
            <button type="button" className="btn" onClick={load}>
              Повторить
            </button>
          </div>
        )}

        {state.status === "loaded" && state.items.length === 0 && (
          <p className="insights-list-empty">
            Сохранённых AI-анализов пока нет. Откройте инструмент и сгенерируйте анализ.
          </p>
        )}

        {state.status === "loaded" && state.items.length > 0 && (
          <ul className="insights-list">
            {state.items.map((item) => {
              const detail = expanded[item.id];
              const mode = modes[item.id] ?? "short";
              return (
                <li key={item.id} className="insights-list-item">
                  <p className="insights-list-item-meta">
                    <Link
                      href={`/instruments/${encodeURIComponent(item.ticker)}`}
                      className="insights-list-item-ticker"
                    >
                      {item.ticker}
                    </Link>
                    <span>{formatTimestamp(item.created_at)}</span>
                    <span>Уверенность: {CONFIDENCE_LABELS[item.confidence]}</span>
                  </p>
                  <p className="insights-list-item-summary">{item.summary}</p>
                  <button type="button" className="btn" onClick={() => toggleExpand(item.id)}>
                    {detail ? "Скрыть" : "Открыть"}
                  </button>

                  {detail && detail.status === "loading" && (
                    <p className="text-muted">Загрузка…</p>
                  )}
                  {detail && detail.status === "error" && (
                    <p className="insights-list-error" role="alert">
                      {detail.message}
                    </p>
                  )}
                  {detail && detail.status === "loaded" && (
                    <InsightDetailBlock
                      detail={detail.data}
                      mode={mode}
                      onModeChange={(nextMode) =>
                        setModes((prev) => ({ ...prev, [item.id]: nextMode }))
                      }
                    />
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </main>
  );
}

function InsightDetailBlock({
  detail,
  mode,
  onModeChange,
}: {
  detail: InsightDetail;
  mode: InsightViewMode;
  onModeChange: (mode: InsightViewMode) => void;
}) {
  return (
    <div className="insights-list-item-detail">
      <ModeToggle mode={mode} onChange={onModeChange} />
      <InsightSections data={detail} mode={mode} />
      <p className="insight-history-detail-provenance">
        {detail.provider} / {detail.model} · prompt {detail.prompt_version} · schema{" "}
        {detail.schema_version}
      </p>
      <p className="insight-history-detail-disclaimer">{detail.disclaimer}</p>
      <Link
        href={`/instruments/${encodeURIComponent(detail.ticker)}`}
        className="insights-list-item-instrument-link"
      >
        Перейти к инструменту {detail.ticker} →
      </Link>
    </div>
  );
}
