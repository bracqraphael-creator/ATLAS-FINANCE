"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { User } from "@supabase/supabase-js";
import type { ImportResult, ModuleManifest, ModuleResult } from "@/lib/types";
import { FAMILIES, UPCOMING } from "@/lib/catalog";
import { createClient } from "@/lib/supabase/client";
import { createPortfolio, listPortfolios, loadPortfolio, saveImport, WRAPPERS, type Portfolio, type PortfolioData } from "@/lib/portfolios";
import { BlockList } from "./blocks/Blocks";
import { ImportWizard } from "./ImportWizard";
import { Logo } from "./Logo";
import { PortfolioDialog } from "./PortfolioDialog";

type Source =
  | { kind: "demo" }
  | { kind: "import"; fileName: string; data: ImportResult }
  | { kind: "portfolio"; portfolio: Portfolio; data: PortfolioData };

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
  const supabase = useMemo(() => createClient(), []);
  const [user, setUser] = useState<User | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [modules, setModules] = useState<ModuleManifest[]>([]);
  const [active, setActive] = useState<string>("overview");
  const [source, setSource] = useState<Source>({ kind: "demo" });
  const [results, setResults] = useState<Record<string, ModuleResult>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [newPortfolioOpen, setNewPortfolioOpen] = useState(false);

  useEffect(() => {
    api<ModuleManifest[]>("modules").then(setModules).catch((e) => setError(e.message));
  }, []);

  // Session : le site reste utilisable sans compte (démonstration, import temporaire)
  useEffect(() => {
    supabase.auth.getUser().then(({ data }) => { setUser(data.user); setAuthReady(true); });
    const { data: sub } = supabase.auth.onAuthStateChange((_e, session) => setUser(session?.user ?? null));
    return () => sub.subscription.unsubscribe();
  }, [supabase]);

  const openPortfolio = useCallback(async (p: Portfolio) => {
    setLoading(true);
    try {
      const data = await loadPortfolio(supabase, p.id);
      setResults({});
      setSource({ kind: "portfolio", portfolio: p, data });
      try { localStorage.setItem("atlas-portfolio", p.id); } catch { /* facultatif */ }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [supabase]);

  // À la connexion : charger les portefeuilles et rouvrir le dernier consulté
  useEffect(() => {
    if (!user) { setPortfolios([]); setSource((s) => (s.kind === "portfolio" ? { kind: "demo" } : s)); return; }
    listPortfolios(supabase).then((list) => {
      setPortfolios(list);
      let last: string | null = null;
      try { last = localStorage.getItem("atlas-portfolio"); } catch { /* facultatif */ }
      const pick = list.find((p) => p.id === last) ?? list[0];
      if (pick) openPortfolio(pick);
    }).catch((e) => setError(e.message));
  }, [user, supabase, openPortfolio]);

  const load = useCallback(async (moduleId: string, src: Source) => {
    if (src.kind === "portfolio" && src.data.transactions.length === 0) { setResults({}); return; }
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

  const onImported = async (data: ImportResult, fileName: string) => {
    if (source.kind === "portfolio") {
      try {
        const { inserted, duplicates } = await saveImport(supabase, source.portfolio.id, data, fileName, source.data.transactions);
        setNotice(`${inserted} opération(s) enregistrée(s) dans ${source.portfolio.name}` +
                  (duplicates ? `, ${duplicates} déjà présente(s) ignorée(s).` : "."));
        await openPortfolio(source.portfolio);
      } catch (e) {
        setError((e as Error).message);
      }
      return;
    }
    setResults({});
    setNotice(null);
    setSource({ kind: "import", fileName, data });
  };

  const onCreatePortfolio = async (name: string, wrapper: string) => {
    const p = await createPortfolio(supabase, name, wrapper);
    setPortfolios((list) => [...list, p]);
    await openPortfolio(p);
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
              {source.kind === "demo" ? "Portefeuille de démonstration, cours fictifs"
               : source.kind === "import" ? `${source.fileName}, non enregistré`
               : `${WRAPPERS.find((w) => w.value === source.portfolio.wrapper)?.label ?? ""}, ${source.data.transactions.length} opération(s)`}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {user && portfolios.length > 0 && (
              <select aria-label="Portefeuille" value={source.kind === "portfolio" ? source.portfolio.id : ""}
                      onChange={(e) => {
                        if (e.target.value === "__new") { setNewPortfolioOpen(true); return; }
                        const p = portfolios.find((x) => x.id === e.target.value);
                        if (p) { setNotice(null); openPortfolio(p); }
                      }}
                      className="max-w-[220px] rounded-lg border border-line bg-panel px-3 py-2 text-sm text-text focus:border-brass focus:outline-none">
                {source.kind !== "portfolio" && <option value="" disabled>Choisir un portefeuille</option>}
                {portfolios.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                <option value="__new">Nouveau portefeuille…</option>
              </select>
            )}
            {source.kind === "import" && (
              <button onClick={() => { setResults({}); setSource({ kind: "demo" }); }}
                      className="rounded-lg border border-line px-3.5 py-2 text-sm text-muted transition-colors hover:border-faint hover:text-text">
                Revenir à la démo
              </button>
            )}
            <button onClick={() => (user && portfolios.length === 0 ? setNewPortfolioOpen(true) : setImportOpen(true))}
                    className="rounded-lg bg-brass px-3.5 py-2 text-sm font-medium text-ink transition-opacity hover:opacity-90">
              Importer des opérations
            </button>
            {authReady && (user ? (
              <Link href="/compte" title={user.email ?? "Mon compte"} aria-label="Mon compte"
                    className="flex h-9 w-9 items-center justify-center rounded-full border border-line text-sm font-medium uppercase text-muted hover:border-faint hover:text-text">
                {(user.email ?? "?").charAt(0)}
              </Link>
            ) : (
              <Link href="/connexion" className="rounded-lg border border-line px-3.5 py-2 text-sm text-muted hover:border-faint hover:text-text">
                Se connecter
              </Link>
            ))}
          </div>
        </header>
        <ImportWizard open={importOpen} onClose={() => setImportOpen(false)} onImported={onImported}
                      target={source.kind === "portfolio" ? source.portfolio.name : null} />
        <PortfolioDialog open={newPortfolioOpen} first={portfolios.length === 0} onClose={() => setNewPortfolioOpen(false)} onCreate={onCreatePortfolio} />

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

          {notice && (
            <p role="status" className="flex items-start justify-between gap-3 rounded-lg border border-gain/30 bg-gain/[0.07] px-4 py-3 text-sm text-gain">
              {notice}
              <button onClick={() => setNotice(null)} aria-label="Fermer" className="text-gain/70 hover:text-gain">✕</button>
            </p>
          )}

          {authReady && !user && source.kind === "import" && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-brass/30 bg-brass/[0.07] px-4 py-3 text-sm">
              <span className="text-text">Cet import n&apos;est pas enregistré : il disparaîtra si vous quittez la page.</span>
              <Link href="/connexion" className="font-medium text-brass hover:underline">Créer un compte pour le conserver</Link>
            </div>
          )}

          {user && portfolios.length === 0 && authReady && (
            <section className="rounded-xl border border-line bg-panel px-6 py-10 text-center">
              <h2 className="text-base font-semibold">Bienvenue sur ATLAS FINANCE</h2>
              <p className="mx-auto mt-1 max-w-[52ch] text-sm text-muted">Créez un portefeuille, puis importez l&apos;export de votre courtier : les analyses se calculent aussitôt. En attendant, la démonstration reste affichée ci-dessous.</p>
              <button onClick={() => setNewPortfolioOpen(true)} className="mt-5 rounded-lg bg-brass px-4 py-2 text-sm font-medium text-ink hover:opacity-90">Créer un portefeuille</button>
            </section>
          )}

          {source.kind === "portfolio" && source.data.transactions.length === 0 && (
            <section className="rounded-xl border border-line bg-panel px-6 py-12 text-center">
              <h2 className="text-base font-semibold">{source.portfolio.name} est vide</h2>
              <p className="mx-auto mt-1 max-w-[50ch] text-sm text-muted">Importez l&apos;export CSV ou Excel de votre courtier pour lancer les analyses.</p>
              <button onClick={() => setImportOpen(true)} className="mt-5 rounded-lg bg-brass px-4 py-2 text-sm font-medium text-ink hover:opacity-90">Importer des opérations</button>
            </section>
          )}

          {error && <p role="alert" className="rounded-lg border border-loss/30 bg-loss/[0.08] px-4 py-3 text-sm text-loss">{error}</p>}

          <div className={`transition-opacity duration-200 ${loading ? "opacity-50" : ""}`} aria-busy={loading}>
            {source.kind === "portfolio" && source.data.transactions.length === 0 ? null
             : current ? <BlockList blocks={current.blocks} asOf={current.data_as_of} />
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
