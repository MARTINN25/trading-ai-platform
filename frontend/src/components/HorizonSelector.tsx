"use client";

import type { AnalysisHorizon } from "@/lib/instrument-api";

/**
 * FR-006 — the user picks a horizon explicitly before every generation
 * (task scope §19); this component never auto-submits and the parent
 * never falls back to a default if none is selected. SHORT is *not* a
 * scalping mode — the hint text states the real 1-5 trading day range,
 * not an intraday/tick framing (task scope §4).
 */
export const HORIZON_HINTS: Record<AnalysisHorizon, string> = {
  short: "1–5 торговых дней",
  medium: "1–8 недель",
  long: "2–12 месяцев",
};

const HORIZON_OPTIONS: { value: AnalysisHorizon; label: string; hint: string }[] = [
  { value: "short", label: "SHORT", hint: HORIZON_HINTS.short },
  { value: "medium", label: "MEDIUM", hint: HORIZON_HINTS.medium },
  { value: "long", label: "LONG", hint: HORIZON_HINTS.long },
];

export default function HorizonSelector({
  horizon,
  onChange,
  disabled,
}: {
  horizon: AnalysisHorizon;
  onChange: (horizon: AnalysisHorizon) => void;
  disabled?: boolean;
}) {
  return (
    <div className="horizon-selector">
      <div className="horizon-selector-buttons" role="radiogroup" aria-label="Горизонт анализа">
        {HORIZON_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={horizon === option.value}
            disabled={disabled}
            className={horizon === option.value ? "horizon-button horizon-button-selected" : "horizon-button"}
            onClick={() => onChange(option.value)}
          >
            <strong>{option.label}</strong>
            <span>{option.hint}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
