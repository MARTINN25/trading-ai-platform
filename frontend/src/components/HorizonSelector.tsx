"use client";

import type { AnalysisHorizon } from "@/lib/instrument-api";

/**
 * FR-006 — the user picks a horizon explicitly before every generation
 * (task scope §19); this component never auto-submits and the parent
 * never falls back to a default if none is selected. SHORT is *not* a
 * scalping mode — the hint text states the real 1-5 trading day range,
 * not an intraday/tick framing (task scope §4).
 */
const HORIZON_OPTIONS: { value: AnalysisHorizon; label: string; hint: string }[] = [
  { value: "short", label: "SHORT", hint: "1–5 торговых дней" },
  { value: "medium", label: "MEDIUM", hint: "1–8 недель" },
  { value: "long", label: "LONG", hint: "2–12 месяцев" },
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
