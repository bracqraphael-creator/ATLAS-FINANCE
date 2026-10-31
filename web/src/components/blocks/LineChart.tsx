"use client";

import { useMemo, useState } from "react";
import { formatAxis, formatDate, formatValue } from "@/lib/format";

const COLORS = ["var(--accent)", "var(--muted)", "var(--positive)", "var(--warning)"];
const W = 720;
const H = 220;
const PAD = { top: 12, right: 12, bottom: 24, left: 72 };

type Props = { series: { name: string; points: [string, number][] }[]; unit: string };

/** Graphique en lignes léger (SVG), sans dépendance. Les graphiques financiers complets
 *  (bougies, indicateurs) utiliseront Lightweight Charts dans le module dédié. */
export function LineChart({ series, unit }: Props) {
  const [hover, setHover] = useState<number | null>(null);

  const { paths, ticks, dates, xs, scaleY } = useMemo(() => {
    const dates = series[0]?.points.map((p) => p[0]) ?? [];
    const all = series.flatMap((s) => s.points.map((p) => p[1]));
    let lo = Math.min(...all);
    let hi = Math.max(...all);
    if (lo === hi) { lo -= 1; hi += 1; }
    const n = Math.max(dates.length - 1, 1);
    const xs = dates.map((_, i) => PAD.left + (i / n) * (W - PAD.left - PAD.right));
    const scaleY = (v: number) => PAD.top + (1 - (v - lo) / (hi - lo)) * (H - PAD.top - PAD.bottom);
    const paths = series.map((s) => s.points.map((p, i) => `${i ? "L" : "M"}${xs[i].toFixed(1)} ${scaleY(p[1]).toFixed(1)}`).join(""));
    const ticks = [0, 0.5, 1].map((t) => lo + t * (hi - lo));
    return { paths, ticks, dates, xs, scaleY };
  }, [series]);

  if (dates.length < 2) return null;

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * W;
    const ratio = (x - PAD.left) / (W - PAD.left - PAD.right);
    setHover(Math.min(dates.length - 1, Math.max(0, Math.round(ratio * (dates.length - 1)))));
  };

  return (
    <div className="rounded-lg border border-border bg-surface p-3">
      <div className="mb-1 flex flex-wrap gap-4 text-xs text-muted">
        {series.map((s, i) => (
          <span key={s.name} className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4" style={{ background: COLORS[i % COLORS.length] }} />
            {s.name}
            {hover !== null && <strong className="text-foreground">{formatValue(s.points[hover][1], unit)}</strong>}
          </span>
        ))}
        {hover !== null && <span className="ml-auto">{formatDate(dates[hover])}</span>}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={series.map((s) => s.name).join(", ")}
           onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={W - PAD.right} y1={scaleY(t)} y2={scaleY(t)} stroke="var(--border)" />
            <text x={PAD.left - 6} y={scaleY(t) + 4} textAnchor="end" fontSize="11" fill="var(--muted)">{formatAxis(t, unit)}</text>
          </g>
        ))}
        {paths.map((d, i) => (
          <path key={i} d={d} fill="none" stroke={COLORS[i % COLORS.length]} strokeWidth={i === 0 ? 1.75 : 1.25} />
        ))}
        <text x={PAD.left} y={H - 6} fontSize="11" fill="var(--muted)">{formatDate(dates[0])}</text>
        <text x={W - PAD.right} y={H - 6} textAnchor="end" fontSize="11" fill="var(--muted)">{formatDate(dates[dates.length - 1])}</text>
        {hover !== null && <line x1={xs[hover]} x2={xs[hover]} y1={PAD.top} y2={H - PAD.bottom} stroke="var(--muted)" strokeDasharray="3 3" />}
      </svg>
    </div>
  );
}
