"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { formatAxis, formatDate, formatValue } from "@/lib/format";

const PAD = { top: 16, right: 8, bottom: 26, left: 56 };

type Props = {
  series: { name: string; points: [string, number][] }[];
  unit: string;
  height?: number;
  /** « loss » : courbe de baisse (drawdown), dessinée en rouge depuis la ligne zéro. */
  tone?: "brass" | "loss";
};

/** Graphique en aire, léger (SVG), avec lecture au survol. */
export function LineChart({ series, unit, height = 240, tone = "brass" }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const [W, setW] = useState(760);   // largeur réelle : le texte garde sa taille sur mobile
  const box = useRef<HTMLElement>(null);
  const gradientId = useId();

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setW(Math.max(280, Math.round(entry.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const H = W < 500 ? Math.round(height * 0.75) : height;
  const color = tone === "loss" ? "var(--loss)" : "var(--brass)";

  const geo = useMemo(() => {
    const dates = series[0]?.points.map((p) => p[0]) ?? [];
    const all = series.flatMap((s) => s.points.map((p) => p[1]));
    let lo = Math.min(...all, tone === "loss" ? 0 : Infinity);
    let hi = Math.max(...all, tone === "loss" ? 0 : -Infinity);
    if (lo === hi) { lo -= 1; hi += 1; }
    const pad = (hi - lo) * 0.06;
    if (tone !== "loss") {
      hi += pad;
      lo = lo >= 0 && lo - pad < 0 ? 0 : lo - pad;   // ne pas descendre sous zéro pour des montants positifs
    }
    const n = Math.max(dates.length - 1, 1);
    const x = (i: number) => PAD.left + (i / n) * (W - PAD.left - PAD.right);
    const y = (v: number) => PAD.top + (1 - (v - lo) / (hi - lo)) * (H - PAD.top - PAD.bottom);
    const lines = series.map((s) => s.points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(p[1]).toFixed(1)}`).join(""));
    const base = tone === "loss" ? y(0) : H - PAD.bottom;
    const area = lines[0] ? `${lines[0]}L${x(dates.length - 1).toFixed(1)} ${base}L${x(0).toFixed(1)} ${base}Z` : "";
    const ticks = [0, 1 / 3, 2 / 3, 1].map((t) => lo + t * (hi - lo));
    return { dates, x, y, lines, area, ticks };
  }, [series, H, tone, W]);

  if (geo.dates.length < 2) return null;
  const { dates, x, y, lines, area, ticks } = geo;

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const ratio = (px - PAD.left) / (W - PAD.left - PAD.right);
    setHover(Math.min(dates.length - 1, Math.max(0, Math.round(ratio * (dates.length - 1)))));
  };

  const shown = hover ?? dates.length - 1;

  return (
    <figure ref={box}>
      <figcaption className="mb-2 flex flex-wrap items-baseline gap-x-5 gap-y-1 text-[13px]">
        {series.map((s, i) => (
          <span key={s.name} className="flex items-center gap-2 text-muted">
            <span className="inline-block h-[2px] w-4 rounded" style={{ background: i === 0 ? color : "var(--faint)" }} />
            {s.name}
            <span className="font-medium text-text">{formatValue(s.points[shown][1], unit)}</span>
          </span>
        ))}
        <span className="ml-auto text-faint">{formatDate(dates[shown])}</span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full touch-none select-none" role="img"
           aria-label={`${series.map((s) => s.name).join(" et ")}, du ${formatDate(dates[0])} au ${formatDate(dates[dates.length - 1])}`}
           onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
        <defs>
          <linearGradient id={gradientId} x1="0" x2="0" y1={tone === "loss" ? "1" : "0"} y2={tone === "loss" ? "0" : "1"}>
            <stop offset="0%" stopColor={color} stopOpacity="0.28" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--line)" strokeWidth="1" />
            <text x={PAD.left - 10} y={y(t) + 4} textAnchor="end" fontSize="11" fill="var(--faint)">{formatAxis(t, unit)}</text>
          </g>
        ))}
        <path d={area} fill={`url(#${gradientId})`} />
        {lines.slice(1).map((d, i) => (
          <path key={i} d={d} fill="none" stroke="var(--faint)" strokeWidth="1.25" strokeDasharray="4 3" />
        ))}
        <path d={lines[0]} fill="none" stroke={color} strokeWidth="1.75" strokeLinejoin="round" />
        <text x={PAD.left} y={H - 6} fontSize="11" fill="var(--faint)">{formatDate(dates[0])}</text>
        <text x={W - PAD.right} y={H - 6} textAnchor="end" fontSize="11" fill="var(--faint)">{formatDate(dates[dates.length - 1])}</text>
        {hover !== null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={H - PAD.bottom} stroke="var(--muted)" strokeWidth="1" strokeDasharray="2 3" />
            <circle cx={x(hover)} cy={y(series[0].points[hover][1])} r="3.5" fill="var(--ink)" stroke={color} strokeWidth="1.75" />
          </g>
        )}
      </svg>
    </figure>
  );
}
