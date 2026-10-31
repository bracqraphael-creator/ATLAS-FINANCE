"use client";

import { useEffect, useMemo, useState } from "react";
import type { ModuleParam } from "@/lib/types";

type Values = Record<string, unknown>;

/** Réglages d'un module (déclarés dans son manifest) : saisie libre, calcul relancé après une courte pause. */
export function ParamsForm({ params: all, values, onChange }: { params: ModuleParam[]; values: Values; onChange: (v: Values) => void }) {
  // La répartition cible a son propre éditeur
  const params = useMemo(() => all.filter((p) => p.type !== "allocation"), [all]);
  const [draft, setDraft] = useState<Record<string, string>>({});

  const valuesKey = JSON.stringify(params.map((p) => values[p.key] ?? null));
  useEffect(() => {
    setDraft(Object.fromEntries(params.map((p) => {
      const v = values[p.key];
      return [p.key, v === null || v === undefined ? "" : Array.isArray(v) ? v.join(", ") : String(v)];
    })));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params, valuesKey]);

  useEffect(() => {
    const handle = setTimeout(() => {
      const next: Values = { ...values };
      for (const p of params) {
        if (p.type === "symbols") {
          const text = (draft[p.key] ?? "").trim();
          next[p.key] = text ? text.split(/[\s,;]+/).filter(Boolean).map((x) => x.toUpperCase()) : null;
          continue;
        }
        const raw = (draft[p.key] ?? "").trim().replace(",", ".");
        if (raw === "") { next[p.key] = p.default === null ? null : p.default; continue; }
        const n = Number(raw);
        if (!Number.isFinite(n)) return;            // saisie en cours (« 1, »…) : on attend
        next[p.key] = n;
      }
      if (JSON.stringify(next) !== JSON.stringify(values)) onChange(next);
    }, 600);
    return () => clearTimeout(handle);
  }, [draft, params, values, onChange]);

  return (
    <details open className="rounded-xl border border-line bg-panel px-5 py-4">
      <summary className="cursor-pointer text-[13px] font-medium text-muted">Réglages</summary>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {params.map((p) => {
          const invalid = p.type !== "symbols" && (() => {
            const raw = (draft[p.key] ?? "").trim().replace(",", ".");
            if (raw === "") return false;
            const n = Number(raw);
            return !Number.isFinite(n) || (p.min !== undefined && n < p.min) || (p.max !== undefined && n > p.max);
          })();
          return (
            <label key={p.key} className={`text-sm ${p.type === "symbols" ? "sm:col-span-2 lg:col-span-3" : ""}`}>
              <span className="mb-1 block text-xs text-faint">{p.label}</span>
              <div className={`flex items-center rounded-lg border bg-ink focus-within:border-brass ${invalid ? "border-loss/60" : "border-line"}`}>
                <input inputMode={p.type === "symbols" ? "text" : "decimal"} value={draft[p.key] ?? ""} placeholder={p.type === "symbols" ? "ex. IE00B4L5Y983, FR001400U5Q4" : p.default === null ? "automatique" : String(p.default)}
                       onChange={(e) => setDraft((d) => ({ ...d, [p.key]: e.target.value }))}
                       aria-invalid={invalid}
                       className="min-w-0 flex-1 bg-transparent px-3 py-2 text-sm text-text placeholder:text-faint focus:outline-none" />
                {p.unit && <span className="pr-3 text-xs text-faint">{p.unit}</span>}
              </div>
              {invalid && <span className="mt-1 block text-xs text-loss">Entre {p.min} et {p.max}</span>}
            </label>
          );
        })}
      </div>
    </details>
  );
}
