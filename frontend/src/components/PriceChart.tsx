"use client";

import { useRef, useState, type MouseEvent } from "react";
import type { InstrumentHistoryPeriod, InstrumentHistoryPoint } from "@/lib/instrument-api";

/**
 * Small hand-rolled SVG chart — still deliberately not a chart library
 * (Phase 1 decision, ADR-0003 §12/§589, reaffirmed here: this remains a
 * bounded, ~100-260 point dataset with no zoom/pan/multi-year
 * virtualization requirement — a plain `<svg>` comfortably covers
 * candlesticks, a volume panel, axes, and hover crosshair without a
 * new dependency).
 *
 * Phase 2B.1 (Professional Instrument Workspace) chart-artifact fix
 * (task scope §5): the previous version placed each point at an
 * x-position proportional to *elapsed wall-clock time*
 * (`(t - minT) / tRange`). For any period whose fetched bars span a
 * real non-trading gap (the 1D period's 100 five-minute bars commonly
 * cover parts of two sessions), that gap — confirmed live as ~17.6
 * real hours between 2026-08-10T19:55Z and 2026-08-11T13:30Z, ~41% of
 * the period's total elapsed time, with the price essentially
 * unchanged across it (308.19 -> 308.24) — was stretched across a
 * proportional share of the chart width, producing exactly the
 * reported "long perfectly horizontal segment". The data itself was
 * never wrong (real, sorted, non-duplicate provider values). The fix
 * is standard practice for intraday multi-session charts: plot by
 * **bar index**, not elapsed time, so every bar gets equal width
 * regardless of the real gap to its neighbor. The gap is not hidden —
 * `SESSION_BREAK_FACTOR` below detects it (any inter-bar gap more than
 * 3x the period's median gap) and draws a labeled dashed break line
 * instead, an honest discontinuity marker rather than a misleading
 * flat segment.
 */

const VIEWBOX_WIDTH = 800;
const PRICE_HEIGHT = 260;
const VOLUME_HEIGHT = 64;
const PANEL_GAP = 10;
const AXIS_HEIGHT = 22;
const LEFT_AXIS_WIDTH = 54;
const RIGHT_PAD = 10;
const TOP_PAD = 12;
const TOTAL_HEIGHT = TOP_PAD + PRICE_HEIGHT + PANEL_GAP + VOLUME_HEIGHT + AXIS_HEIGHT;
const VOLUME_TOP = TOP_PAD + PRICE_HEIGHT + PANEL_GAP;

// A gap more than 3x the period's own median inter-bar gap is treated
// as a real session/data break, not just normal spacing jitter —
// deterministic and period-agnostic (no hardcoded market-hours
// assumption baked in).
const SESSION_BREAK_FACTOR = 3;

const timeOnlyFormatter = new Intl.DateTimeFormat("ru-RU", { timeStyle: "short" });
const dateTimeFormatter = new Intl.DateTimeFormat("ru-RU", { dateStyle: "short", timeStyle: "short" });
const dateOnlyFormatter = new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium" });

export function formatPointTimestamp(t: number, period: InstrumentHistoryPeriod): string {
  const date = new Date(t);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  if (period === "1D") return timeOnlyFormatter.format(date);
  if (period === "1M") return dateOnlyFormatter.format(date);
  return dateTimeFormatter.format(date);
}

interface ParsedPoint {
  index: number;
  t: number;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume: number | null;
}

function toFiniteOrNull(value: string | null): number | null {
  if (value === null) return null;
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

function parsePoints(points: InstrumentHistoryPoint[]): ParsedPoint[] {
  const parsed: ParsedPoint[] = [];
  for (const point of points) {
    const t = new Date(point.timestamp).getTime();
    const close = Number(point.close);
    // Defensive: a point this chart can't safely plot is skipped, not
    // turned into NaN coordinates — malformed data must never crash
    // the chart or draw a misleading line.
    if (!Number.isFinite(t) || !Number.isFinite(close)) continue;
    parsed.push({
      index: parsed.length,
      t,
      open: toFiniteOrNull(point.open),
      high: toFiniteOrNull(point.high),
      low: toFiniteOrNull(point.low),
      close,
      volume: point.volume,
    });
  }
  return parsed;
}

function medianGap(parsed: ParsedPoint[]): number {
  if (parsed.length < 2) return 0;
  const gaps: number[] = [];
  for (let i = 1; i < parsed.length; i++) gaps.push(parsed[i].t - parsed[i - 1].t);
  gaps.sort((a, b) => a - b);
  return gaps[Math.floor(gaps.length / 2)];
}

function formatPrice(value: number): string {
  return value.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function PriceChart({
  points,
  period,
}: {
  points: InstrumentHistoryPoint[];
  period: InstrumentHistoryPeriod;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const parsed = parsePoints(points);

  if (parsed.length === 0) {
    return <p className="price-chart-empty">Нет данных.</p>;
  }

  const n = parsed.length;
  const plotLeft = LEFT_AXIS_WIDTH;
  const plotRight = VIEWBOX_WIDTH - RIGHT_PAD;
  const plotWidth = plotRight - plotLeft;

  function xForIndex(index: number): number {
    if (n === 1) return plotLeft + plotWidth / 2;
    return plotLeft + (index / (n - 1)) * plotWidth;
  }

  const hasFullOhlc = parsed.every((p) => p.open !== null && p.high !== null && p.low !== null);
  const highs = parsed.map((p) => (hasFullOhlc ? (p.high as number) : p.close));
  const lows = parsed.map((p) => (hasFullOhlc ? (p.low as number) : p.close));
  const maxPrice = Math.max(...highs);
  const minPrice = Math.min(...lows);
  const rawRange = maxPrice - minPrice;
  const priceRange = rawRange > 0 ? rawRange : Math.max(Math.abs(maxPrice) * 0.01, 0.01);
  const paddedMin = minPrice - priceRange * 0.1;
  const paddedMax = maxPrice + priceRange * 0.1;
  const paddedRange = paddedMax - paddedMin || 1;

  function yForPrice(price: number): number {
    return TOP_PAD + PRICE_HEIGHT - ((price - paddedMin) / paddedRange) * PRICE_HEIGHT;
  }

  const hasAnyVolume = parsed.some((p) => p.volume !== null);
  const maxVolume = Math.max(1, ...parsed.map((p) => p.volume ?? 0));

  function volumeBarHeight(volume: number): number {
    return (volume / maxVolume) * VOLUME_HEIGHT;
  }

  const direction = parsed[n - 1].close >= parsed[0].close ? "up" : "down";
  const directionLabel = direction === "up" ? "рост" : "падение или без изменений";
  const lastClose = parsed[n - 1].close;
  const lastY = yForPrice(lastClose);

  const priceTickCount = 4;
  const priceTicks = Array.from({ length: priceTickCount + 1 }, (_, i) => paddedMin + (paddedRange * i) / priceTickCount);

  const timeTickCount = Math.min(6, n);
  const timeTickIndices = Array.from(
    new Set(
      Array.from({ length: timeTickCount }, (_, i) => Math.round((i / Math.max(1, timeTickCount - 1)) * (n - 1)))
    )
  );

  const gap = medianGap(parsed);
  const breakIndices: number[] =
    gap > 0
      ? parsed.slice(1).reduce<number[]>((acc, p, i) => {
          if (p.t - parsed[i].t > gap * SESSION_BREAK_FACTOR) acc.push(p.index);
          return acc;
        }, [])
      : [];

  const candleWidth = Math.max(1.5, Math.min(10, (plotWidth / n) * 0.7));

  function handleMouseMove(event: MouseEvent<SVGSVGElement>): void {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    if (rect.width === 0) return;
    const scaleX = VIEWBOX_WIDTH / rect.width;
    const xInViewBox = (event.clientX - rect.left) * scaleX;
    const relative = (xInViewBox - plotLeft) / plotWidth;
    const idx = Math.round(relative * (n - 1));
    setHoverIndex(Math.max(0, Math.min(n - 1, idx)));
  }

  function handleMouseLeave(): void {
    setHoverIndex(null);
  }

  const hovered = hoverIndex !== null ? parsed[hoverIndex] : null;

  return (
    <div className="price-chart-wrap">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${VIEWBOX_WIDTH} ${TOTAL_HEIGHT}`}
        className={`price-chart-svg price-chart-${direction}`}
        role="img"
        aria-label={`График цены, ${n} точек: ${directionLabel}. Последняя цена ${formatPrice(lastClose)}.`}
        preserveAspectRatio="none"
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
      >
        {priceTicks.map((price, i) => {
          const y = yForPrice(price);
          return (
            <g key={i}>
              <line x1={plotLeft} y1={y} x2={plotRight} y2={y} className="price-chart-gridline" />
              <text
                x={plotLeft - 6}
                y={y}
                textAnchor="end"
                dominantBaseline="middle"
                className="price-chart-axis-label"
              >
                {price.toFixed(2)}
              </text>
            </g>
          );
        })}

        {breakIndices.map((idx) => {
          const x = xForIndex(idx - 0.5);
          return (
            <line
              key={`break-${idx}`}
              x1={x}
              y1={TOP_PAD}
              x2={x}
              y2={VOLUME_TOP + VOLUME_HEIGHT}
              className="price-chart-session-break"
            />
          );
        })}

        <line
          x1={plotLeft}
          y1={lastY}
          x2={plotRight}
          y2={lastY}
          className="price-chart-last-price-line"
        />
        {/* A small filled backing rect keeps the label readable over
            candles/gridlines instead of floating bare text (task scope
            §6: "last-price marker" polish). */}
        <rect
          x={plotRight - 44}
          y={Math.max(TOP_PAD, lastY - 15)}
          width={44}
          height={13}
          rx={2}
          className="price-chart-last-price-label-bg"
        />
        <text
          x={plotRight - 4}
          y={Math.max(TOP_PAD + 9, lastY - 6)}
          textAnchor="end"
          className="price-chart-last-price-label"
        >
          {formatPrice(lastClose)}
        </text>
        <circle cx={xForIndex(n - 1)} cy={lastY} r={2.5} className="price-chart-last-price-dot" />

        {hasFullOhlc
          ? parsed.map((p) => {
              const x = xForIndex(p.index);
              const openY = yForPrice(p.open as number);
              const closeY = yForPrice(p.close);
              const highY = yForPrice(p.high as number);
              const lowY = yForPrice(p.low as number);
              const up = p.close >= (p.open as number);
              const bodyTop = Math.min(openY, closeY);
              const bodyHeight = Math.max(1, Math.abs(closeY - openY));
              return (
                <g key={p.index} className={up ? "price-chart-candle-up" : "price-chart-candle-down"}>
                  <line x1={x} y1={highY} x2={x} y2={lowY} className="price-chart-wick" />
                  <rect
                    x={x - candleWidth / 2}
                    y={bodyTop}
                    width={candleWidth}
                    height={bodyHeight}
                    className="price-chart-candle-body"
                  />
                </g>
              );
            })
          : (
              <path
                d={parsed
                  .map((p, i) => `${i === 0 ? "M" : "L"}${xForIndex(p.index).toFixed(2)},${yForPrice(p.close).toFixed(2)}`)
                  .join(" ")}
                fill="none"
                strokeWidth={2}
                className="price-chart-line"
              />
            )}

        {hasAnyVolume &&
          parsed.map((p) => {
            if (p.volume === null) return null;
            const x = xForIndex(p.index);
            const h = volumeBarHeight(p.volume);
            const up = hasFullOhlc ? p.close >= (p.open as number) : true;
            return (
              <rect
                key={`v-${p.index}`}
                x={x - candleWidth / 2}
                y={VOLUME_TOP + VOLUME_HEIGHT - h}
                width={candleWidth}
                height={h}
                className={up ? "price-chart-volume-bar-up" : "price-chart-volume-bar-down"}
              />
            );
          })}

        {timeTickIndices.map((idx) => (
          <text
            key={idx}
            x={xForIndex(idx)}
            y={TOTAL_HEIGHT - 5}
            textAnchor="middle"
            className="price-chart-axis-label"
          >
            {formatPointTimestamp(parsed[idx].t, period)}
          </text>
        ))}

        {hovered && (
          <line
            x1={xForIndex(hovered.index)}
            y1={TOP_PAD}
            x2={xForIndex(hovered.index)}
            y2={VOLUME_TOP + VOLUME_HEIGHT}
            className="price-chart-crosshair"
          />
        )}
      </svg>

      {/* A compact, labeled OHLC readout — stacked label/value pairs
          like a terminal quote strip, not an inline sentence (task
          scope §6: "avoid long inline sentence formatting"). */}
      <div className="price-chart-tooltip" aria-live="polite">
        {hovered ? (
          <div className="price-chart-tooltip-grid">
            <span className="price-chart-tooltip-time">{formatPointTimestamp(hovered.t, period)}</span>
            {hasFullOhlc ? (
              <>
                <span className="price-chart-tooltip-cell">
                  <span className="price-chart-tooltip-label">O</span>
                  <span className="price-chart-tooltip-value">{formatPrice(hovered.open as number)}</span>
                </span>
                <span className="price-chart-tooltip-cell">
                  <span className="price-chart-tooltip-label">H</span>
                  <span className="price-chart-tooltip-value">{formatPrice(hovered.high as number)}</span>
                </span>
                <span className="price-chart-tooltip-cell">
                  <span className="price-chart-tooltip-label">L</span>
                  <span className="price-chart-tooltip-value">{formatPrice(hovered.low as number)}</span>
                </span>
                <span className="price-chart-tooltip-cell">
                  <span className="price-chart-tooltip-label">C</span>
                  <span className="price-chart-tooltip-value">{formatPrice(hovered.close)}</span>
                </span>
              </>
            ) : (
              <span className="price-chart-tooltip-cell">
                <span className="price-chart-tooltip-label">C</span>
                <span className="price-chart-tooltip-value">{formatPrice(hovered.close)}</span>
              </span>
            )}
            {hovered.volume !== null && (
              <span className="price-chart-tooltip-cell">
                <span className="price-chart-tooltip-label">Vol</span>
                <span className="price-chart-tooltip-value">{hovered.volume.toLocaleString("ru-RU")}</span>
              </span>
            )}
          </div>
        ) : (
          <span className="price-chart-tooltip-hint">Наведите на график для деталей по бару</span>
        )}
      </div>

      {!hasAnyVolume && <p className="price-chart-volume-unavailable">Объём по этому периоду недоступен.</p>}
    </div>
  );
}
