"use client";

import { useCallback, useEffect, useState } from "react";
import type { ImportResult, ModuleManifest, ModuleResult } from "@/lib/types";
import { FAMILIES, UPCOMING } from "@/lib/catalog";
import { BlockList } from "./blocks/Blocks";
import { Logo } from "./Logo";

type Source = { kind: "demo" } | { kind: "import"; fileName: string; data: ImportResult };

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/engine/${path}`, init);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail ?? `Erreur ${res.status}`);
  return body as T;
}

function familyOf(m: ModuleManifest): string {
  return FAMILIES.some((f) => f.id === m.family) ? m.family : "portefeuille";
}

export function Dashboard() {
  const [modules, setModules] = useState<ModuleManifest[]>([]);
  const [active, setActive] = useState<string>("overview");
  const [source, setSource] = useState<Source>({ kind: "demo" });
  const [results, setResults] = useState<Record<string, ModuleResult>>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api<ModuleManifest[]>("modules").then(setModules).catch((e) => setError(e.message));
  }, []);

  const load = useCallback(async (moduleId: string, src: Source) => {
    setLoading(true);
    setError(null);
    try {
      const result = src.kind === "demo"
        ? await api<ModuleResult>(`demo/${moduleId}`)
        : await api<ModuleResult>(`compute/${moduleId}`, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ transactions: src.data.transactions, instruments: src.data.instruments }),
          });
      setResults((r) => ({ ...r, [moduleId]: result }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(active, source); }, [active, source, load]);

  const onFile = async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    try {
      const data = await api<ImportResult>("imports", { method: "POST", body: form });
      if (data.transactions.length === 0) {
        setError(`Aucune opération lisible dans ${file.name}. ${data.rejected[0]?.reason ?? ""}`);
        return;
      }
      setResults({});
      setSource({ kind: "import", fileName: file.name, data });
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const current = results[active];
  const spec = modules.find((m) => m.id === active);

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[248px_1fr]">
      {/* Navigation */}
      <aside className="border-b border-line bg-ink lg:sticky lg:top-0 lg:h-screen lg:overflow-y-auto lg:border-b-0 lg:border-r">
        <div className="flex items-center gap-2.5 px-5 py-5">
          <Logo />
          <span className="text-[15px] font-semibold tracking-[0.08em]">ATLAS</span>
          <span className="text-[15px] font-normal tracking-[0.08em] text-muted">FINANCE</span>
        </div>

        <nav aria-label="Modules" className="flex gap-1 overflow-x-auto px-3 pb-3 lg:block lg:space-y-6 lg:px-3 lg:pb-8 lg:pt-2">
          {FAMILIES.map((f) => {
            const live = modules.filter((m) => familyOf(m) === f.id);
            const soon = UPCOMING.filter((u) => u.family === f.id);
            return (
              <div key={f.id} className="contents lg:block">
                <div className="hidden px-2 pb-2 text-xs text-faint lg:block">{f.label}</div>
                {live.map((m) => (
                  <button key={m.id} onClick={() => setActive(m.id)} aria-current={active === m.id ? "page" : undefined}
                          className={`relative flex shrink-0 items-center lg:w-full whitespace-nowrap rounded-md px-3 py-2 text-left text-sm transition-colors ${
                            active === m.id ? "bg-panel-raised text-text" : "text-muted hover:bg-panel hover:text-text"}`}>
                    {active === m.id && <span className="absolute inset-y-2 left-0 w-[2px] rounded-full bg-brass" aria-hidden="true" />}
                    {m.texts.title ?? m.name}
                  </button>
                ))}
                {soon.map((u) => (
                  <div key={u.name} className="hidden items-center justify-between px-3 py-2 text-sm text-faint lg:flex" title="Module prévu">
                    {u.name}
                    <span className="rounded border border-line px-1.5 py-px text-[10.5px]">Bientôt</span>
                  </div>
                ))}
              </div>
            );
          })}
        </nav>
      </aside>

      {/* Contenu */}
      <div className="min-w-0">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4 sm:px-8">
          <div className="min-w-0">
            <h1 className="text-lg font-semibold tracking-tight">{spec?.texts.title ?? spec?.name ?? "Tableau de bord"}</h1>
            <p className="truncate text-[13px] text-muted">
              {source.kind === "demo" ? "Portefeuille de démonstration, cours fictifs" : source.fileName}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {source.kind === "import" && (
              <button onClick={() => { setResults({}); setSource({ kind: "demo" }); }}
                      className="rounded-lg border border-line px-3.5 py-2 text-sm text-muted transition-colors hover:border-faint hover:text-text">
                Revenir à la démo
              </button>
            )}
            <label className="cursor-pointer rounded-lg bg-brass px-3.5 py-2 text-sm font-medium text-ink transition-opacity focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-brass hover:opacity-90">
              Importer un fichier CSV
              <input type="file" accept=".csv,text/csv" className="sr-only"
                     onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = ""; }} />
            </label>
          </div>
        </header>

        <main className="mx-auto max-w-[1180px] space-y-5 px-5 py-6 sm:px-8 sm:py-8">
          {spec?.texts.description && <p className="max-w-[68ch] text-sm text-muted">{spec.texts.description}</p>}

          {source.kind === "import" && source.data.rejected.length > 0 && (
            <details className="rounded-lg border border-warn/30 bg-warn/[0.07] px-4 py-3 text-sm text-warn">
              <summary className="cursor-pointer">{source.data.rejected.length} ligne(s) ignorée(s) à l&apos;import</summary>
              <ul className="mt-2 list-disc space-y-0.5 pl-5">
                {source.data.rejected.map((r) => <li key={r.line}>Ligne {r.line} : {r.reason}</li>)}
              </ul>
            </details>
          )}

          {error && <p role="alert" className="rounded-lg border border-loss/30 bg-loss/[0.08] px-4 py-3 text-sm text-loss">{error}</p>}

          <div className={`transition-opacity duration-200 ${loading ? "opacity-50" : ""}`} aria-busy={loading}>
            {current ? <BlockList blocks={current.blocks} asOf={current.data_as_of} />
                     : !error && <p className="py-16 text-center text-sm text-muted">Calcul en cours…</p>}
          </div>

          {current?.method && (
            <details className="rounded-xl border border-line px-5 py-4 text-sm text-muted">
              <summary className="cursor-pointer text-text">Méthode de calcul</summary>
              <p className="mt-2 max-w-[80ch] leading-relaxed">{current.method}</p>
            </details>
          )}

          <footer className="pt-2 text-xs text-faint">{current?.disclaimer ?? "Ceci n'est pas un conseil en investissement."}</footer>
        </main>
      </div>
    </div>
  );
}
