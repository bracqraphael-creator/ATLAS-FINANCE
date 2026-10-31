import type { AllocationBlock } from "@/lib/types";
import { formatValue } from "@/lib/format";

// Teintes dérivées du laiton et du bleu nuit, de la plus forte à la plus discrète.
export const SLICE_COLORS = ["#c9a45c", "#7d93b8", "#4fbf8f", "#b07fb8", "#5fa8b5", "#8a7a5c", "#56607a"];

/** Anneau de répartition, avec légende chiffrée à côté. */
export function Donut({ block }: { block: AllocationBlock }) {
  const R = 52;
  const C = 2 * Math.PI * R;
  let offset = 0;
  const top = block.slices[0];
  return (
    <div className="flex items-center gap-6">
      <svg viewBox="0 0 140 140" className="h-36 w-36 shrink-0 -rotate-90" role="img"
           aria-label={block.slices.map((s) => `${s.label} ${formatValue(s.weight * 100, "%")}`).join(", ")}>
        <circle cx="70" cy="70" r={R} fill="none" stroke="var(--line)" strokeWidth="14" />
        {block.slices.map((s, i) => {
          const len = s.weight * C;
          const el = (
            <circle key={s.label} cx="70" cy="70" r={R} fill="none" stroke={SLICE_COLORS[i % SLICE_COLORS.length]}
                    strokeWidth="14" strokeDasharray={`${Math.max(len - 2, 0.5)} ${C}`} strokeDashoffset={-offset} />
          );
          offset += len;
          return el;
        })}
        <g className="rotate-90" style={{ transformOrigin: "70px 70px" }}>
          <text x="70" y="68" textAnchor="middle" fontSize="20" fontWeight="600" fill="var(--text)">
            {Math.round((top?.weight ?? 0) * 100)} %
          </text>
          <text x="70" y="86" textAnchor="middle" fontSize="10.5" fill="var(--muted)">{top?.label}</text>
        </g>
      </svg>
      <ul className="min-w-0 flex-1 space-y-2 text-sm">
        {block.slices.map((s, i) => (
          <li key={s.label} className="flex items-center gap-2.5">
            <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: SLICE_COLORS[i % SLICE_COLORS.length] }} />
            <span className="truncate text-text">{s.label}</span>
            <span className="ml-auto text-muted">{formatValue(s.weight * 100, "%")}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
