"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  evaluateInsight,
  getInsightDetail,
  getInsightEvaluation,
  getInstrumentInsights,
  recordInsightOutcome,
  InstrumentApiError,
  type InsightDetail,
  type InsightEvaluation,
  type InsightRating,
  type InsightSummary,
  type InstrumentConfidenceLevel,
} from "@/lib/instrument-api";
import InsightSections, { ModeToggle, type InsightViewMode } from "@/components/InsightSections";
import ForecastCard, {
  DIRECTIONAL_CLASS,
  DIRECTIONAL_LABELS,
  FORECAST_STATE_LABELS,
  HORIZON_LABELS,
} from "@/components/ForecastCard";
import type { ForecastState } from "@/lib/instrument-api";

type HistoryState =
  | { status: "loading" }
  | { status: "loaded"; items: InsightSummary[] }
  | { status: "error"; message: string };

type DetailState =
  | { status: "loading" }
  | { status: "loaded"; data: InsightDetail }
  | { status: "error"; message: string };

/**
 * Distinct from `DetailState`'s "error" — a `404` here almost always
 * means "never evaluated yet" (see `getInsightEvaluation`'s own
 * docstring), which is a normal, expected state, not a failure.
 */
type EvaluationState =
  | { status: "loading" }
  | { status: "not_evaluated" }
  | { status: "loaded"; data: InsightEvaluation }
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

const RATING_LABELS: Record<InsightRating, string> = {
  useful: "Полезен",
  partially_useful: "Частично полезен",
  not_useful: "Не полезен",
};

const RATING_ORDER: InsightRating[] = ["useful", "partially_useful", "not_useful"];

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
  // FR-021/022 — same presentation-only semantics as `AiAnalysisSection`
  // (task scope §7): default "Кратко" per item, local UI state only.
  const [modes, setModes] = useState<Record<number, InsightViewMode>>({});
  const [evaluations, setEvaluations] = useState<Record<number, EvaluationState>>({});
  const [ratingPending, setRatingPending] = useState<Record<number, boolean>>({});
  const [outcomeDrafts, setOutcomeDrafts] = useState<Record<number, string>>({});
  const [outcomePending, setOutcomePending] = useState<Record<number, boolean>>({});
  const [outcomeErrors, setOutcomeErrors] = useState<Record<number, string | null>>({});

  const load = useCallback(() => {
    setState({ status: "loading" });
    setExpanded({});
    setModes({});
    setEvaluations({});
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

  function loadEvaluation(id: number): void {
    setEvaluations((prev) => ({ ...prev, [id]: { status: "loading" } }));
    getInsightEvaluation(id)
      .then((data) => setEvaluations((prev) => ({ ...prev, [id]: { status: "loaded", data } })))
      .catch((error: unknown) => {
        if (error instanceof InstrumentApiError && error.kind === "not-found") {
          setEvaluations((prev) => ({ ...prev, [id]: { status: "not_evaluated" } }));
          return;
        }
        const message =
          error instanceof InstrumentApiError ? error.message : "Не удалось загрузить оценку.";
        setEvaluations((prev) => ({ ...prev, [id]: { status: "error", message } }));
      });
  }

  function toggleExpand(id: number): void {
    if (expanded[id]) {
      setExpanded((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      setEvaluations((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      setOutcomeDrafts((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      setOutcomeErrors((prev) => {
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
    setExpanded((prev) => ({ ...prev, [id]: { status: "loading" } }));
    setModes((prev) => ({ ...prev, [id]: "short" }));
    getInsightDetail(id)
      .then((data) => setExpanded((prev) => ({ ...prev, [id]: { status: "loaded", data } })))
      .catch((error: unknown) => {
        const message =
          error instanceof InstrumentApiError ? error.message : "Не удалось загрузить инсайт.";
        setExpanded((prev) => ({ ...prev, [id]: { status: "error", message } }));
      });
    loadEvaluation(id);
  }

  function handleRate(id: number, rating: InsightRating): void {
    setRatingPending((prev) => ({ ...prev, [id]: true }));
    evaluateInsight(id, rating)
      .then((data) => setEvaluations((prev) => ({ ...prev, [id]: { status: "loaded", data } })))
      .catch((error: unknown) => {
        const message =
          error instanceof InstrumentApiError ? error.message : "Не удалось сохранить оценку.";
        setEvaluations((prev) => ({ ...prev, [id]: { status: "error", message } }));
      })
      .finally(() => setRatingPending((prev) => ({ ...prev, [id]: false })));
  }

  function handleOutcomeSubmit(id: number): void {
    const note = (outcomeDrafts[id] ?? "").trim();
    if (!note) {
      setOutcomeErrors((prev) => ({ ...prev, [id]: "Введите результат перед сохранением." }));
      return;
    }
    setOutcomeErrors((prev) => ({ ...prev, [id]: null }));
    setOutcomePending((prev) => ({ ...prev, [id]: true }));
    recordInsightOutcome(id, note)
      .then((data) => {
        setEvaluations((prev) => ({ ...prev, [id]: { status: "loaded", data } }));
        setOutcomeDrafts((prev) => ({ ...prev, [id]: "" }));
      })
      .catch((error: unknown) => {
        const message =
          error instanceof InstrumentApiError ? error.message : "Не удалось зафиксировать результат.";
        setOutcomeErrors((prev) => ({ ...prev, [id]: message }));
      })
      .finally(() => setOutcomePending((prev) => ({ ...prev, [id]: false })));
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
              const mode = modes[item.id] ?? "short";
              const evaluation = evaluations[item.id];
              const isRatingPending = ratingPending[item.id] === true;
              const isOutcomePending = outcomePending[item.id] === true;
              const outcomeError = outcomeErrors[item.id];
              const outcomeDraft = outcomeDrafts[item.id] ?? "";
              return (
                <li key={item.id} className="insight-history-item">
                  {/* Compact timeline row (task scope §14): time + chips
                      first, a short verdict line second — never a
                      paragraph as the first thing in the row. Legacy
                      (pre-Phase-2B) rows have no horizon/forecast_state
                      to build chips from, so they fall back to the
                      original plain meta+summary line, honestly. */}
                  {item.horizon !== null && item.forecast_state !== null ? (
                    <>
                      <div className="insight-history-row">
                        <span className="insight-history-time">{formatTimestamp(item.created_at)}</span>
                        <span className="insight-history-chip insight-history-chip--horizon">
                          {HORIZON_LABELS[item.horizon]}
                        </span>
                        {item.forecast_state === "forecast" && item.directional_view ? (
                          <span
                            className={`insight-history-chip ${DIRECTIONAL_CLASS[item.directional_view]}`}
                          >
                            {DIRECTIONAL_LABELS[item.directional_view]}
                          </span>
                        ) : (
                          <span className="insight-history-chip insight-history-chip--state">
                            {FORECAST_STATE_LABELS[item.forecast_state as Exclude<ForecastState, "forecast">]}
                          </span>
                        )}
                        <span className="insight-history-chip">{CONFIDENCE_LABELS[item.confidence]}</span>
                      </div>
                      <p className="insight-history-item-verdict">{item.concise_verdict || item.summary}</p>
                    </>
                  ) : (
                    <>
                      <p className="insight-history-item-meta">
                        {formatTimestamp(item.created_at)} · Уверенность:{" "}
                        <span
                          className={`insight-history-confidence insight-history-confidence-${item.confidence}`}
                        >
                          {CONFIDENCE_LABELS[item.confidence]}
                        </span>
                      </p>
                      <p className="insight-history-item-summary">{item.summary}</p>
                    </>
                  )}
                  <button type="button" className="insight-history-toggle" onClick={() => toggleExpand(item.id)}>
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
                      {/* Phase 2B: only rendered for insights saved after
                          this task — a pre-Phase-2B row has `horizon ===
                          null` and simply falls through to the original
                          FR-018 sections below unchanged (task scope §17). */}
                      {detail.data.horizon !== null && detail.data.forecast_state !== null && (
                          <ForecastCard
                            data={{
                              horizon: detail.data.horizon,
                              forecast_state: detail.data.forecast_state,
                              directional_view: detail.data.directional_view,
                              confidence: detail.data.confidence,
                              concise_verdict: detail.data.concise_verdict ?? "",
                              base_case: detail.data.base_case,
                              bullish_case: detail.data.bullish_case,
                              bearish_case: detail.data.bearish_case,
                              catalysts: detail.data.catalysts,
                              invalidation_conditions: detail.data.invalidation_conditions,
                              what_to_watch_next: detail.data.what_to_watch_next,
                              data_freshness: detail.data.data_freshness,
                              check_after: detail.data.check_after,
                              uncertainty: detail.data.uncertainty,
                              context_categories_used: detail.data.context_categories_used,
                              key_facts: detail.data.key_facts,
                              key_drivers: detail.data.key_drivers,
                            }}
                          />
                        )}
                      {/* Legacy FR-018 content — preserved, visually
                          secondary (Professional Instrument Workspace,
                          task scope §12-§13), same collapsible pattern
                          as the fresh-generation view. Pre-Phase-2B
                          rows (`horizon === null`, no `ForecastCard`
                          above) still show this expanded-by-default via
                          `open`, since it is the *only* content they have. */}
                      <details className="ai-analysis-detail" open={detail.data.horizon === null}>
                        <summary>Подробный анализ (10 разделов FR-018)</summary>
                        <div className="ai-analysis-detail-body">
                          <ModeToggle
                            mode={mode}
                            onChange={(nextMode) => setModes((prev) => ({ ...prev, [item.id]: nextMode }))}
                          />
                          <InsightSections data={detail.data} mode={mode} />
                        </div>
                      </details>
                      <p className="insight-history-detail-provenance">
                        {detail.data.provider} / {detail.data.model} · prompt{" "}
                        {detail.data.prompt_version} · schema {detail.data.schema_version}
                      </p>
                      <p className="insight-history-detail-disclaimer">{detail.data.disclaimer}</p>

                      {/* UJ-017 alt flow: "создание записи со ссылкой на
                          ранее сформированный инсайт" — the journal page
                          re-validates insight_id itself; only the ticker
                          string and a numeric id travel through this link,
                          never insight content (task scope §14). */}
                      <Link
                        href={`/journal?ticker=${encodeURIComponent(ticker)}&insight_id=${item.id}`}
                        className="insight-history-add-to-journal"
                      >
                        Добавить в дневник
                      </Link>

                      <div className="insight-evaluation">
                        <h3>Оценка инсайта</h3>
                        {(!evaluation || evaluation.status === "loading") && (
                          <p className="insight-evaluation-loading">Загрузка оценки…</p>
                        )}
                        {evaluation && evaluation.status === "error" && (
                          <div className="insight-evaluation-error" role="alert">
                            <p>{evaluation.message}</p>
                            <button type="button" onClick={() => loadEvaluation(item.id)}>
                              Повторить
                            </button>
                          </div>
                        )}
                        {evaluation &&
                          (evaluation.status === "loaded" || evaluation.status === "not_evaluated") && (
                            <>
                              <div className="insight-evaluation-buttons" role="group" aria-label="Оценка инсайта">
                                {RATING_ORDER.map((ratingValue) => {
                                  const currentRating =
                                    evaluation.status === "loaded" ? evaluation.data.rating : null;
                                  const isSelected = currentRating === ratingValue;
                                  return (
                                    <button
                                      key={ratingValue}
                                      type="button"
                                      disabled={isRatingPending}
                                      aria-pressed={isSelected}
                                      className={
                                        isSelected
                                          ? "insight-evaluation-rating-selected"
                                          : "insight-evaluation-rating"
                                      }
                                      onClick={() => handleRate(item.id, ratingValue)}
                                    >
                                      {RATING_LABELS[ratingValue]}
                                    </button>
                                  );
                                })}
                              </div>
                              {evaluation.status === "loaded" && evaluation.data.rating !== null && (
                                <p className="insight-evaluation-saved">
                                  Оценка сохранена: {RATING_LABELS[evaluation.data.rating]}.
                                </p>
                              )}
                            </>
                          )}
                      </div>

                      <div className="insight-outcome">
                        <h3>Результат</h3>
                        {evaluation &&
                          evaluation.status === "loaded" &&
                          evaluation.data.outcome_note !== null &&
                          evaluation.data.outcome_recorded_at !== null && (
                            <p className="insight-outcome-recorded">
                              {formatTimestamp(evaluation.data.outcome_recorded_at)}:{" "}
                              {evaluation.data.outcome_note}
                            </p>
                          )}
                        {evaluation && (evaluation.status === "loaded" || evaluation.status === "not_evaluated") && (
                          <div className="insight-outcome-form">
                            <textarea
                              aria-label="Результат по инсайту"
                              placeholder="Что произошло по факту? Например: цена выросла на 3%, инсайт подтвердился."
                              value={outcomeDraft}
                              disabled={isOutcomePending}
                              onChange={(event) =>
                                setOutcomeDrafts((prev) => ({ ...prev, [item.id]: event.target.value }))
                              }
                            />
                            {outcomeError && (
                              <p className="insight-outcome-error" role="alert">
                                {outcomeError}
                              </p>
                            )}
                            <button
                              type="button"
                              disabled={isOutcomePending}
                              onClick={() => handleOutcomeSubmit(item.id)}
                            >
                              {isOutcomePending
                                ? "Сохранение…"
                                : evaluation.status === "loaded" && evaluation.data.outcome_note !== null
                                  ? "Обновить результат"
                                  : "Зафиксировать результат"}
                            </button>
                          </div>
                        )}
                      </div>
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
