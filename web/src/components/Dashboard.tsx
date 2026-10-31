"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { User } from "@supabase/supabase-js";
import type { AccountPlan, ImportResult, ModuleManifest, ModuleResult } from "@/lib/types";
import { FAMILIES, UPCOMING } from "@/lib/catalog";
import { createClient } from "@/lib/supabase/client";
import { createPortfolio, deleteImport, deleteTransactions, listPortfolios, loadPortfolio, saveImport, WRAPPERS, type Portfolio, type PortfolioData } from "@/lib/portfolios";
import { BlockList } from "./blocks/Blocks";
import { AlertsPanel } from "./AlertsPanel";
import { ImportWizard } from "./ImportWizard";
import { OperationsPanel, txKey } from "./OperationsPanel";
import { ParamsForm } from "./ParamsForm";
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
  const [opsOpen, setOpsOpen] = useState(false);
  const [alertsOpen, setAlertsOpen] = useState(false);
  // Réglages par module (valeurs par défaut du manifest, puis saisies de l'utilisateur, mémorisées)
  const [paramValues, setParamValues] = useState<Record<string, Record<string, number | null>>>({});
  const [accountFilter, setAccountFilter] = useState("");   // import non enregistré : un compte ou tous

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

  // Seule la dernière demande compte : une réponse plus ancienne (portefeuille ou compte précédent) est ignorée
  const latest = useRef(0);
  const load = useCallback(async (moduleId: string, src: Source, params: Record<string, number | null> = {}) => {
    const ticket = ++latest.current;
    if (src.kind === "portfolio" && src.data.transactions.length === 0) { setResults({}); return; }
    setLoading(true);
    setError(null);
    try {
      const hasParams = Object.keys(params).length > 0;
      const result = src.kind === "demo"
        ? (hasParams
            ? await api<ModuleResult>(`demo/${moduleId}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ params }) })
            : await api<ModuleResult>(`demo/${moduleId}`))
        : await api<ModuleResult>(`compute/${moduleId}`, {
            method: "POST",
            headers: { "content-type": "application/json" },
            // Les identifiants de base ne servent pas au calcul
            body: JSON.stringify({ transactions: src.data.transactions, instruments: src.data.instruments, params },
                                 (k, v) => (k === "id" || k === "importId" ? undefined : v)),
          });
      if (ticket === latest.current) setResults((r) => ({ ...r, [moduleId]: result }));
    } catch (e) {
      if (ticket === latest.current) setError((e as Error).message);
    } finally {
      if (ticket === latest.current) setLoading(false);
    }
  }, []);

  // Import non enregistré à plusieurs comptes : les analyses portent sur le compte choisi
  const computed = useMemo<Source>(() => {
    if (source.kind !== "import" || !accountFilter) return source;
    return { ...source, data: { ...source.data, transactions: source.data.transactions.filter((t) => t.account === accountFilter) } };
  }, [source, accountFilter]);

  const activeSpec = modules.find((m) => m.id === active);
  const activeParams = useMemo(() => {
    const declared = activeSpec?.params ?? [];
    if (!declared.length) return {};
    const saved = paramValues[active];
    return saved ?? Object.fromEntries(declared.map((p) => [p.key, p.default]));
  }, [activeSpec, paramValues, active]);

  // Réglages mémorisés d'une visite à l'autre (navigateur de l'utilisateur)
  useEffect(() => {
    try { const v = localStorage.getItem("atlas-params"); if (v) setParamValues(JSON.parse(v)); } catch { /* facultatif */ }
  }, []);
  const changeParams = useCallback((v: Record<string, number | null>) => {
    setParamValues((all) => {
      const next = { ...all, [active]: v };
      try { localStorage.setItem("atlas-params", JSON.stringify(next)); } catch { /* facultatif */ }
      return next;
    });
  }, [active]);

  useEffect(() => { load(active, computed, activeParams); }, [active, computed, load, activeParams]);

  /** Fichier à plusieurs comptes : chaque compte va dans le portefeuille choisi (créé au besoin). */
  const saveByAccount = async (data: ImportResult, fileName: string, plan: AccountPlan[]) => {
    const current = source.kind === "portfolio" ? source.portfolio : null;
    const lines: string[] = [];
    let created: Portfolio[] = [];
    let main: Portfolio | null = null;
    let mainCount = -1;
    for (const p of plan) {
      let target: Portfolio | undefined;
      if (p.destination.kind === "existing") {
        const id = p.destination.id;
        target = portfolios.find((x) => x.id === id);
      } else {
        target = await createPortfolio(supabase, p.destination.name || p.label, p.destination.wrapper);
        created = [...created, target];
      }
      if (!target) continue;
      const transactions = data.transactions.filter((t) => t.account === p.label);
      const symbols = new Set(transactions.map((t) => t.symbol).filter(Boolean));
      const instruments = Object.fromEntries(Object.entries(data.instruments).filter(([k]) => symbols.has(k)));
      const existing = current && target.id === current.id && source.kind === "portfolio"
        ? source.data.transactions : (await loadPortfolio(supabase, target.id)).transactions;
      const { inserted, duplicates } = await saveImport(supabase, target.id, { ...data, transactions, instruments }, fileName, existing);
      lines.push(`${p.label} → ${target.name} : ${inserted} opération(s)` + (duplicates ? `, ${duplicates} déjà présente(s)` : ""));
      if (p.count > mainCount) { main = target; mainCount = p.count; }
    }
    // Opérations sans compte (rares) : portefeuille courant
    const orphans = data.transactions.filter((t) => !t.account);
    if (orphans.length && current && source.kind === "portfolio") {
      const { inserted } = await saveImport(supabase, current.id, { ...data, transactions: orphans }, fileName, source.data.transactions);
      lines.push(`sans compte → ${current.name} : ${inserted} opération(s)`);
    }
    if (created.length) setPortfolios((list) => [...list, ...created]);
    setNotice(lines.join(" ; ") + ".");
    if (main) await openPortfolio(main);
  };

  const onImported = async (data: ImportResult, fileName: string, plan?: AccountPlan[]) => {
    if (user && plan?.length) {
      try { await saveByAccount(data, fileName, plan); } catch (e) { setError((e as Error).message); }
      return;
    }
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
    setAccountFilter("");
    setSource({ kind: "import", fileName, data });
  };

  const onDeleteTransactions = async (keys: string[]) => {
    const drop = new Set(keys);
    if (source.kind === "portfolio") {
      await deleteTransactions(supabase, keys);
      setNotice(`${keys.length} opération(s) supprimée(s) de ${source.portfolio.name}.`);
      await openPortfolio(source.portfolio);
    } else if (source.kind === "import") {
      const transactions = source.data.transactions.filter((t, i) => !drop.has(txKey(t, i)));
      setResults({});
      setSource({ ...source, data: { ...source.data, transactions } });
      setNotice(`${keys.length} opération(s) retirée(s) de l'import.`);
    }
  };

  const onDeleteImport = async (id: string) => {
    if (source.kind !== "portfolio") return;
    const imp = source.data.imports.find((i) => i.id === id);
    await deleteImport(supabase, id);
    setNotice(`Import « ${imp?.file_path || "sans nom"} » supprimé avec ses ${imp?.lines ?? 0} opération(s).`);
    await openPortfolio(source.portfolio);
  };

  const onCreatePortfolio = async (name: string, wrapper: string) => {
    const p = await createPortfolio(supabase, name, wrapper);
    setPortfolios((list) => [...list, p]);
    await openPortfolio(p);
  };

  // Lignes détenues du portefeuille ouvert (quantités recalculées depuis les opérations), pour cibler une alerte
  const heldLines = useMemo(() => {
    if (source.kind !== "portfolio") return [];
    const qty = new Map<string, number>();
    const names = new Map<string, string>();
    for (const t of [...source.data.transactions].sort((a, b) => (a.date < b.date ? -1 : 1))) {
      if (!t.symbol) continue;
      const q = qty.get(t.symbol) ?? 0;
      if (t.type === "buy") qty.set(t.symbol, q + t.quantity);
      else if (t.type === "sell") qty.set(t.symbol, Math.max(q - t.quantity, 0));
      else if (t.type === "split" && t.quantity > 0) qty.set(t.symbol, q * t.quantity);
      if (t.name) names.set(t.symbol, t.name);
    }
    return [...qty].filter(([, q]) => q > 1e-9).map(([symbol]) => ({
      symbol, name: source.data.instruments[symbol]?.name ?? names.get(symbol) ?? symbol,
    })).sort((a, b) => a.name.localeCompare(b.name, "fr"));
  }, [source]);

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
            {user && source.kind === "portfolio" && source.data.transactions.length > 0 && (
              <button onClick={() => setAlertsOpen(true)}
                      className="rounded-lg border border-line px-3.5 py-2 text-sm text-muted transition-colors hover:border-faint hover:text-text">
                Alertes
              </button>
            )}
            {source.kind !== "demo" && source.data.transactions.length > 0 && (
              <button onClick={() => setOpsOpen(true)}
                      className="rounded-lg border border-line px-3.5 py-2 text-sm text-muted transition-colors hover:border-faint hover:text-text">
                Opérations
              </button>
            )}
            {source.kind === "import" && source.data.accounts?.length > 1 && (
              <select aria-label="Compte affiché" value={accountFilter}
                      onChange={(e) => { setResults({}); setAccountFilter(e.target.value); }}
                      className="max-w-[220px] rounded-lg border border-line bg-panel px-3 py-2 text-sm text-text focus:border-brass focus:outline-none">
                <option value="">Tous les comptes</option>
                {source.data.accounts.map((a) => <option key={a.label} value={a.label}>{a.label} ({a.count})</option>)}
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
                      target={source.kind === "portfolio" ? source.portfolio.name : null}
                      portfolios={user ? portfolios : undefined}
                      currentId={source.kind === "portfolio" ? source.portfolio.id : null}
                      currentEmpty={source.kind === "portfolio" && source.data.transactions.length === 0} />
        {source.kind !== "demo" && (
          <OperationsPanel open={opsOpen} onClose={() => setOpsOpen(false)}
                           title={source.kind === "portfolio" ? source.portfolio.name : source.fileName}
                           transactions={source.data.transactions}
                           imports={source.kind === "portfolio" ? source.data.imports : null}
                           onDeleteTransactions={onDeleteTransactions} onDeleteImport={onDeleteImport} />
        )}
        {user && source.kind === "portfolio" && (
          <AlertsPanel open={alertsOpen} onClose={() => setAlertsOpen(false)} supabase={supabase}
                       portfolio={source.portfolio} lines={heldLines} email={user.email ?? null} />
        )}
        <PortfolioDialog open={newPortfolioOpen} first={portfolios.length === 0} onClose={() => setNewPortfolioOpen(false)} onCreate={onCreatePortfolio} />

        <main className="mx-auto max-w-[1180px] space-y-5 px-5 py-6 sm:px-8 sm:py-8">
          {spec?.texts.description && <p className="max-w-[68ch] text-sm text-muted">{spec.texts.description}</p>}
          {spec?.params && spec.params.length > 0 && (
            <ParamsForm params={spec.params} values={activeParams} onChange={changeParams} />
          )}

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
              <p className="mx-auto mt-1 max-w-[50ch] text-sm text-muted">Importez l&apos;export CSV, Excel ou PDF de votre courtier pour lancer les analyses.</p>
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
