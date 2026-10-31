"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { BarsBlock } from "@/lib/types";
import { formatAxis, formatValue } from "@/lib/format";

const PAD = { top: 22, right: 8, bottom: 26, left: 56 };

/** Histogramme vertical (montants par année), valeurs négatives sous la ligne zéro. */
export function ColumnChart({ block, height = 220 }: { block: BarsBlock; height?: number }) {
  const [W, setW] = useState(560);
  const [hover, setHover] = useState<number | null>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setW(Math.max(260, Math.round(entry.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const { bars, unit } = block;
  // Gains et pertes (valeurs signées) en vert et rouge ; montants toujours positifs (revenus) en laiton
  const signed = bars.some((b) => b.value < 0);

  const geo = useMemo(() => {
    const values = bars.map((b) => b.value);
    let hi = Math.max(0, ...values);
    let lo = Math.min(0, ...values);
    if (hi === lo) hi = 1;
    const span = hi - lo;
    hi += span * 0.08;
    if (lo < 0) lo -= span * 0.08;
    const innerW = W - PAD.left - PAD.right;
    const innerH = height - PAD.top - PAD.bottom;
    const y = (v: number) => PAD.top + ((hi - v) / (hi - lo)) * innerH;
    const slot = innerW / Math.max(bars.length, 1);
    const barW = Math.min(56, slot * 0.62);
    const ticks = [lo, lo + (hi - lo) / 3, lo + (2 * (hi - lo)) / 3, hi].map((t) => (Math.abs(t) < span * 1e-6 ? 0 : t));
    return { y, slot, barW, ticks };
  }, [bars, W, height]);

  const showValues = geo.slot > 44;

  return (
    <div ref={box} className="relative">
      <svg width={W} height={height} role="img" aria-label={`${block.title} : ${bars.map((b) => `${b.label} ${formatValue(b.value, unit)}`).join(", ")}`}>
        {geo.ticks.map((t, i) => (
          <g key={i}>
            <line x1={PAD.left} x2={W - PAD.right} y1={geo.y(t)} y2={geo.y(t)} stroke="var(--line)" strokeDasharray="2 4" />
            <text x={PAD.left - 8} y={geo.y(t) + 4} textAnchor="end" fontSize="11" fill="var(--faint)">{formatAxis(t, unit)}</text>
          </g>
        ))}
        <line x1={PAD.left} x2={W - PAD.right} y1={geo.y(0)} y2={geo.y(0)} stroke="var(--muted)" strokeOpacity="0.5" />
        {bars.map((b, i) => {
          const cx = PAD.left + geo.slot * (i + 0.5);
          const top = geo.y(Math.max(b.value, 0));
          const h = Math.max(Math.abs(geo.y(b.value) - geo.y(0)), b.value === 0 ? 0 : 1.5);
          const fill = signed ? (b.value >= 0 ? "var(--gain)" : "var(--loss)") : "var(--brass)";
          return (
            <g key={b.label} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect x={cx - geo.slot / 2} y={PAD.top} width={geo.slot} height={height - PAD.top - PAD.bottom} fill="transparent" />
              <rect x={cx - geo.barW / 2} y={top} width={geo.barW} height={h} rx="3"
                    fill={fill} fillOpacity={hover === null || hover === i ? 0.9 : 0.45} />
              {(showValues || hover === i) && b.value !== 0 && (
                <text x={cx} y={b.value >= 0 ? top - 6 : top + h + 13} textAnchor="middle" fontSize="11" fill="var(--text)">
                  {formatValue(b.value, unit)}
                </text>
              )}
              <text x={cx} y={height - 8} textAnchor="middle" fontSize="11" fill={hover === i ? "var(--text)" : "var(--faint)"}>{b.label}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
