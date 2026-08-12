"use client";

import type { InstrumentDetails } from "@/lib/instrument-api";
import type { ActivePeriodHistory } from "@/components/PriceChartSection";

/**
 * Compact market snapshot (Professional Instrument Workspace, task
 * scope §9) — two groups:
 *
 * 1. "Текущая сессия" — the already-fetched quote snapshot
 *    (`InstrumentDetails`), unchanged data, just re-laid-out.
 * 2. "Диапазон периода" — deterministically derived from whichever
 *    chart period is currently loaded (`ActivePeriodHistory`, reported
 *    by `PriceChartSection`) — period high/low (from real per-bar
 *    `high`/`low` when the period has full OHLC, falling back to
 *    `close` honestly when it doesn't), distance from each, and where
 *    the current price sits within that range. Never fabricates P/E,
 *    market cap, beta, or any field not actually returned by the
 *    already-approved provider integration (task scope §9).
 */

const UNAVAILABLE = "—";

function parseNumber(value: string): number | null {
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

function formatPrice(value: number | null): string {
  if (value === null) return UNAVAILABLE;
  return value.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatVolume(value: number | null): string {
  if (value === null) return UNAVAILABLE;
  return value.toLocaleString("ru-RU");
}

function formatPercent(value: number | null): string {
  if (value === null) return UNAVAILABLE;
  const sign = value > 0 ? "+" : value < 0 ? "" : "±";
  return `${sign}${value.toFixed(2)}%`;
}

interface PeriodRange {
  high: number;
  low: number;
  usingCloseOnly: boolean;
  pointsCount: number;
}

function computePeriodRange(history: ActivePeriodHistory | null): PeriodRange | null {
  if (!history || history.data.points.length === 0) return null;
  const points = history.data.points;
  const hasFullOhlc = points.every((p) => p.high !== null && p.low !== null);
  const highs: number[] = [];
  const lows: number[] = [];
  for (const p of points) {
    const close = parseNumber(p.close);
    const high = hasFullOhlc && p.high !== null ? parseNumber(p.high) : close;
    const low = hasFullOhlc && p.low !== null ? parseNumber(p.low) : close;
    if (high !== null) highs.push(high);
    if (low !== null) lows.push(low);
  }
  if (highs.length === 0 || lows.length === 0) return null;
  return {
    high: Math.max(...highs),
    low: Math.min(...lows),
    usingCloseOnly: !hasFullOhlc,
    pointsCount: points.length,
  };
}

export default function MarketSnapshotPanel({
  data,
  periodHistory,
}: {
  data: InstrumentDetails;
  periodHistory: ActivePeriodHistory | null;
}) {
  const price = parseNumber(data.price);
  const open = data.open !== null ? parseNumber(data.open) : null;
  const high = data.high !== null ? parseNumber(data.high) : null;
  const low = data.low !== null ? parseNumber(data.low) : null;
  const previousClose = data.previous_close !== null ? parseNumber(data.previous_close) : null;

  const range = computePeriodRange(periodHistory);
  const distanceFromHigh =
    price !== null && range && range.high > 0 ? ((price - range.high) / range.high) * 100 : null;
  const distanceFromLow =
    price !== null && range && range.low > 0 ? ((price - range.low) / range.low) * 100 : null;
  const positionInRange =
    price !== null && range && range.high > range.low
      ? Math.min(100, Math.max(0, ((price - range.low) / (range.high - range.low)) * 100))
      : null;

  return (
    <div className="market-snapshot">
      <div className="market-snapshot-group">
        <h3 className="market-snapshot-group-title">Текущая сессия</h3>
        <dl className="market-snapshot-grid">
          <div className="market-snapshot-item">
            <dt>Open</dt>
            <dd>{formatPrice(open)}</dd>
          </div>
          <div className="market-snapshot-item">
            <dt>High</dt>
            <dd>{formatPrice(high)}</dd>
          </div>
          <div className="market-snapshot-item">
            <dt>Low</dt>
            <dd>{formatPrice(low)}</dd>
          </div>
          <div className="market-snapshot-item">
            <dt>Prev close</dt>
            <dd>{formatPrice(previousClose)}</dd>
          </div>
          <div className="market-snapshot-item">
            <dt>Volume</dt>
            <dd>{formatVolume(data.volume)}</dd>
          </div>
        </dl>
      </div>

      <div className="market-snapshot-group">
        <h3 className="market-snapshot-group-title">
          Диапазон периода {periodHistory ? `(${periodHistory.period})` : ""}
        </h3>
        {range ? (
          <>
            <dl className="market-snapshot-grid">
              <div className="market-snapshot-item">
                <dt>Максимум периода</dt>
                <dd>{formatPrice(range.high)}</dd>
              </div>
              <div className="market-snapshot-item">
                <dt>Минимум периода</dt>
                <dd>{formatPrice(range.low)}</dd>
              </div>
              <div className="market-snapshot-item">
                <dt>От максимума</dt>
                <dd>{formatPercent(distanceFromHigh)}</dd>
              </div>
              <div className="market-snapshot-item">
                <dt>От минимума</dt>
                <dd>{formatPercent(distanceFromLow)}</dd>
              </div>
            </dl>
            {positionInRange !== null && (
              <div className="market-snapshot-range-bar" aria-hidden="true">
                <div className="market-snapshot-range-bar-track">
                  <div
                    className="market-snapshot-range-bar-marker"
                    style={{ left: `${positionInRange}%` }}
                  />
                </div>
                <div className="market-snapshot-range-bar-labels">
                  <span>{formatPrice(range.low)}</span>
                  <span>{formatPrice(range.high)}</span>
                </div>
              </div>
            )}
            {range.usingCloseOnly && (
              <p className="market-snapshot-note">
                Диапазон по ценам закрытия — детальный OHLC для этого периода недоступен.
              </p>
            )}
          </>
        ) : (
          <p className="market-snapshot-note">Загрузка диапазона периода…</p>
        )}
      </div>

      <p className="market-snapshot-source">
        Источник: {data.source === "twelvedata" ? "Twelve Data" : data.source}
      </p>
    </div>
  );
}
