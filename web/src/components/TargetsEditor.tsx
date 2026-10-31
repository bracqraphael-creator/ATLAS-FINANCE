"use client";

import { useEffect, useState } from "react";
import type { Allocation } from "@/lib/targets";
import { formatValue } from "@/lib/format";

type Line = { symbol: string; name: string; current?: number };

/** Saisie de la répartition cible : un poids en % par ligne, total affiché, lignes à ajouter par code ISIN. */
export function TargetsEditor({ lines, value, onApply, saving }: {
  lines: Line[]; value: Allocation | null; onApply: (a: Allocation) => Promise<void> | void; saving?: boolean;
}) {
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [extra, setExtra] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const base: Record<string, string> = {};
    for (const l of lines) base[l.symbol] = value?.[l.symbol] !== undefined ? String(value[l.symbol])
      : value ? "" : l.current !== undefined ? String(Math.round(l.current)) : "";
    for (const [s, w] of Object.entries(value ?? {})) if (!(s in base)) base[s] = String(w);
    setDraft(base);
  }, [lines, value]);

  const parsed = Object.fromEntries(Object.entries(draft).map(([s, v]) => [s, Number(v.replace(",", "."))])
    .filter(([, n]) => Number.isFinite(n as number) && (n as number) > 0)) as Allocation;
  const total = Object.values(parsed).reduce((a, b) => a + b, 0);
  const names = new Map(lines.map((l) => [l.symbol, l.name]));

  return (
    <details open className="rounded-xl border border-line bg-panel px-5 py-4">
      <summary className="cursor-pointer text-[13px] font-medium text-muted">Répartition cible</summary>
      <div className="mt-3 space-y-2">
        {Object.keys(draft).map((s) => (
          <div key={s} className="grid grid-cols-[minmax(0,1fr)_110px_auto] items-center gap-3 text-sm">
            <span className="truncate text-text" title={names.get(s) ?? s}>{names.get(s) ?? s}</span>
            <div className="flex items-center rounded-lg border border-line bg-ink focus-within:border-brass">
              <input inputMode="decimal" value={draft[s]} aria-label={`Poids cible de ${names.get(s) ?? s}`}
                     onChange={(e) => setDraft((d) => ({ ...d, [s]: e.target.value }))}
                     className="w-full min-w-0 bg-transparent px-3 py-1.5 text-right text-sm text-text focus:outline-none" />
              <span className="pr-3 text-xs text-faint">%</span>
            </div>
            <span className="w-16 text-right text-xs text-faint">
              {lines.find((l) => l.symbol === s)?.current !== undefined ? `${formatValue(lines.find((l) => l.symbol === s)!.current!)} % auj.` : ""}
            </span>
          </div>
        ))}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <input value={extra} onChange={(e) => setExtra(e.target.value)} placeholder="Ajouter un titre (code ISIN)"
                 className="min-w-[200px] flex-1 rounded-lg border border-line bg-ink px-3 py-1.5 text-sm text-text placeholder:text-faint" />
          <button onClick={() => { const c = extra.trim().toUpperCase(); if (c) { setDraft((d) => ({ ...d, [c]: "" })); setExtra(""); } }}
                  className="rounded-lg border border-line px-3 py-1.5 text-[13px] text-muted hover:border-faint hover:text-text">Ajouter</button>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3">
          <span className={`text-sm ${Math.abs(total - 100) < 0.01 ? "text-gain" : "text-warn"}`}>
            Total : {formatValue(total)} %{Math.abs(total - 100) >= 0.01 && total > 0 ? " (sera ramené à 100 %)" : ""}
          </span>
          <div className="flex items-center gap-3">
            {message && <span className="text-xs text-muted">{message}</span>}
            <button disabled={!total || saving}
                    onClick={async () => { await onApply(parsed); setMessage("Répartition cible enregistrée."); }}
                    className="rounded-lg bg-brass px-4 py-2 text-sm font-medium text-ink hover:opacity-90 disabled:opacity-40">
              Enregistrer la cible
            </button>
          </div>
        </div>
      </div>
    </details>
  );
}
