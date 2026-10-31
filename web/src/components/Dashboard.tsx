"use client";

import { useCallback, useEffect, useState } from "react";
import type { ImportResult, ModuleManifest, ModuleResult } from "@/lib/types";
import { BlockList } from "./blocks/Blocks";

type Source = { kind: "demo" } | { kind: "import"; fileName: string; data: ImportResult };

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/engine/${path}`, init);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail ?? `Erreur ${res.status}`);
  return body as T;
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
    <div className="mx-auto max-w-6xl px-4 py-6">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">ATLAS FINANCE</h1>
          <p className="text-xs text-muted">
            {source.kind === "demo" ? "Portefeuille de démonstration, cours fictifs" : `Fichier importé : ${source.fileName}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {source.kind === "import" && (
            <button onClick={() => { setResults({}); setSource({ kind: "demo" }); }}
                    className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-surface">
              Revenir à la démo
            </button>
          )}
          <label className="cursor-pointer rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white hover:opacity-90">
            Importer un CSV
            <input type="file" accept=".csv,text/csv" className="hidden"
                   onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = ""; }} />
          </label>
        </div>
      </header>

      {source.kind === "import" && source.data.rejected.length > 0 && (
        <details className="mb-4 rounded-md bg-warning/10 px-3 py-2 text-xs text-warning">
          <summary>{source.data.rejected.length} ligne(s) ignorée(s) à l&apos;import</summary>
          <ul className="mt-1 list-disc pl-5">
            {source.data.rejected.map((r) => <li key={r.line}>Ligne {r.line} : {r.reason}</li>)}
          </ul>
        </details>
      )}

      <nav className="mb-5 flex gap-1 overflow-x-auto border-b border-border">
        {modules.map((m) => (
          <button key={m.id} onClick={() => setActive(m.id)}
                  className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm ${active === m.id ? "border-accent font-medium" : "border-transparent text-muted hover:text-foreground"}`}>
            {m.texts.title ?? m.name}
          </button>
        ))}
      </nav>

      {error && <p className="mb-4 rounded-md bg-negative/10 px-3 py-2 text-sm text-negative">{error}</p>}

      <main className={`rounded-xl border border-border bg-surface p-5 transition-opacity ${loading ? "opacity-60" : ""}`}>
        {spec?.texts.description && <p className="mb-4 text-sm text-muted">{spec.texts.description}</p>}
        {current ? <BlockList blocks={current.blocks} asOf={current.data_as_of} /> : !error && <p className="text-sm text-muted">Calcul en cours…</p>}
        {current && (
          <details className="mt-5 text-xs text-muted">
            <summary className="cursor-pointer">Méthode de calcul</summary>
            <p className="mt-1">{current.method}</p>
          </details>
        )}
      </main>

      <footer className="mt-6 text-xs text-muted">{current?.disclaimer ?? "Ceci n'est pas un conseil en investissement."}</footer>
    </div>
  );
}
