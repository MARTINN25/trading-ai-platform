import type { InstrumentHistoryPoint } from "@/lib/instrument-api";

/**
 * Small hand-rolled SVG line chart — deliberately not a chart library.
 *
 * Decision (task scope §7): compared a lightweight-charts/Recharts
 * dependency against a small local component for this first,
 * line-only, no-zoom/pan/indicators chart. `frontend/package.json`
 * has exactly three runtime dependencies today (next/react/react-dom)
 * — this codebase's established pattern is "no dependency unless a
 * vertical slice genuinely needs it" (ADR-0003 §12/§589: charting
 * library explicitly left for "a separate task/ADR as a vertical
 * slice becomes ready" — this is that task, and a single close-price
 * polyline doesn't need canvas rendering, an imperative lifecycle API,
 * or a D3-based dependency tree). A plain `<svg>` is SSR-safe with no
 * client-only bootstrapping, has no accessibility surprises (`role`/
 * `aria-label` work exactly like any other element), and keeps the
 * bundle unchanged. If a future task needs zoom/pan, candlesticks, or
 * indicators, that is a real reason to revisit lightweight-charts.
 */

const VIEWBOX_WIDTH = 600;
const VIEWBOX_HEIGHT = 200;
const PADDING = 8;

interface ParsedPoint {
  t: number;
  close: number;
}

function parsePoints(points: InstrumentHistoryPoint[]): ParsedPoint[] {
  const parsed: ParsedPoint[] = [];
  for (const point of points) {
    const t = new Date(point.timestamp).getTime();
    const close = Number(point.close);
    // Defensive: a point this chart can't safely plot is skipped, not
    // turned into NaN coordinates — malformed data must never crash
    // the chart or draw a misleading line.
    if (Number.isFinite(t) && Number.isFinite(close)) {
      parsed.push({ t, close });
    }
  }
  return parsed;
}

export default function PriceChart({ points }: { points: InstrumentHistoryPoint[] }) {
  const parsed = parsePoints(points);

  if (parsed.length === 0) {
    return <p className="price-chart-empty">Нет данных.</p>;
  }

  const closes = parsed.map((point) => point.close);
  const minClose = Math.min(...closes);
  const maxClose = Math.max(...closes);
  const closeRange = maxClose - minClose;

  const minT = parsed[0].t;
  const maxT = parsed[parsed.length - 1].t;
  const tRange = maxT - minT;

  function xFor(t: number): number {
    // Single point / all-identical-timestamp: center it instead of
    // dividing by zero.
    if (tRange === 0) return VIEWBOX_WIDTH / 2;
    return PADDING + ((t - minT) / tRange) * (VIEWBOX_WIDTH - 2 * PADDING);
  }

  function yFor(close: number): number {
    // Flat/near-flat data (all closes equal): draw a flat horizontal
    // line instead of dividing by zero.
    if (closeRange === 0) return VIEWBOX_HEIGHT / 2;
    return (
      VIEWBOX_HEIGHT -
      PADDING -
      ((close - minClose) / closeRange) * (VIEWBOX_HEIGHT - 2 * PADDING)
    );
  }

  const direction = closes[closes.length - 1] >= closes[0] ? "up" : "down";
  const directionLabel = direction === "up" ? "рост" : "падение или без изменений";

  if (parsed.length === 1) {
    const cx = xFor(parsed[0].t);
    const cy = yFor(parsed[0].close);
    return (
      <svg
        viewBox={`0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`}
        className="price-chart-svg"
        role="img"
        aria-label="График цены: доступна только одна точка данных"
        preserveAspectRatio="none"
      >
        <circle cx={cx} cy={cy} r={3} className="price-chart-point" />
      </svg>
    );
  }

  const path = parsed
    .map((point, index) => `${index === 0 ? "M" : "L"}${xFor(point.t).toFixed(2)},${yFor(point.close).toFixed(2)}`)
    .join(" ");

  return (
    <svg
      viewBox={`0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`}
      className={`price-chart-svg price-chart-${direction}`}
      role="img"
      aria-label={`График цены за период, ${parsed.length} точек: ${directionLabel}`}
      preserveAspectRatio="none"
    >
      <path d={path} fill="none" strokeWidth={2} className="price-chart-line" />
    </svg>
  );
}
