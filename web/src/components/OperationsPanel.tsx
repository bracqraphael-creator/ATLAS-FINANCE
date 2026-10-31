"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Transaction } from "@/lib/types";
import type { ImportRecord } from "@/lib/portfolios";
import { formatCell, formatDate, TYPE_LABELS } from "@/lib/format";

/** Clé stable d'une opération : identifiant en base, ou position dans un import non enregistré. */
export const txKey = (t: Transaction, index: number) => t.id ?? `local-${index}`;

type Props = {
  open: boolean;
  onClose: () => void;
  title: string;
  transactions: Transaction[];
  imports: ImportRecord[] | null;      // null : import non enregistré (suppression locale)
  formatLabels?: Record<string, string>;
  onDeleteTransactions: (keys: string[]) => Promise<void>;
  onDeleteImport?: (id: string) => Promise<void>;
};

const PAGE = 100;

export function OperationsPanel({ open, onClose, title, transactions, imports, onDeleteTransactions, onDeleteImport }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [query, setQuery] = useState("");
  const [type, setType] = useState<string>("");
  const [importFilter, setImportFilter] = useState<string>("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [limit, setLimit] = useState(PAGE);
  const [confirm, setConfirm] = useState<{ kind: "selection" } | { kind: "import"; id: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const d = dialog.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
    if (!open) { setSelected(new Set()); setConfirm(null); setError(null); setQuery(""); setType(""); setImportFilter(""); setLimit(PAGE); }
  }, [open]);

  // Les opérations les plus récentes en premier
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return transactions
      .map((t, i) => ({ t, key: txKey(t, i) }))
      .filter(({ t }) => (!type || t.type === type)
        && (!importFilter || (importFilter === "__none" ? !t.importId : t.importId === importFilter))
        && (!q || `${t.name ?? ""} ${t.symbol ?? ""}`.toLowerCase().includes(q)))
      .sort((a, b) => (a.t.date < b.t.date ? 1 : a.t.date > b.t.date ? -1 : 0));
  }, [transactions, query, type, importFilter]);

  const visible = rows.slice(0, limit);
  const allVisibleSelected = visible.length > 0 && visible.every((r) => selected.has(r.key));
  const orphanCount = imports ? transactions.filter((t) => !t.importId).length : 0;

  const toggle = (key: string) => setSelected((s) => {
    const n = new Set(s);
    if (n.has(key)) n.delete(key); else n.add(key);
    return n;
  });

  const run = async (action: () => Promise<void>) => {
    setBusy(true); setError(null);
    try {
      await action();
      setSelected(new Set());
      setConfirm(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const importToDelete = confirm?.kind === "import" ? imports?.find((i) => i.id === confirm.id) : null;

  return (
    <dialog ref={dialog} onClose={onClose} aria-labelledby="ops-title"
            className="m-auto w-[min(1080px,calc(100vw-24px))] max-h-[calc(100vh-24px)] overflow-hidden rounded-2xl border border-line bg-panel p-0 text-text backdrop:bg-black/60 backdrop:backdrop-blur-[2px]">
      <div className="flex max-h-[calc(100vh-24px)] flex-col">
        <header className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
          <div>
            <h2 id="ops-title" className="text-base font-semibold">Opérations de {title}</h2>
            <p className="mt-0.5 text-[13px] text-muted">
              {transactions.length} opération(s){imports ? `, ${imports.length} import(s)` : ", import non enregistré"}.
              Les analyses se recalculent après chaque suppression.
            </p>
          </div>
          <button onClick={onClose} aria-label="Fermer" className="rounded-md px-2 py-1 text-muted hover:bg-panel-raised hover:text-text">✕</button>
        </header>

        <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-6 py-5">
          {error && <p role="alert" className="rounded-lg border border-loss/30 bg-loss/[0.08] px-4 py-3 text-sm text-loss">{error}</p>}

          {imports && imports.length > 0 && (
            <section>
              <h3 className="mb-2 text-[13px] font-medium text-muted">Imports</h3>
              <ul className="divide-y divide-line rounded-lg border border-line">
                {imports.slice().reverse().map((imp) => (
                  <li key={imp.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                    <div className="min-w-0">
                      <div className="truncate text-sm">{imp.file_path || "Import sans nom"}</div>
                      <div className="text-xs text-faint">
                        {new Date(imp.created_at).toLocaleDateString("fr-FR", { day: "2-digit", month: "long", year: "numeric" })}
                        {" · "}{imp.lines} opération(s)
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button onClick={() => { setImportFilter(imp.id); setLimit(PAGE); }}
                              className="rounded-md border border-line px-3 py-1.5 text-[13px] text-muted hover:border-faint hover:text-text">
                        Voir les lignes
                      </button>
                      <button onClick={() => setConfirm({ kind: "import", id: imp.id })}
                              className="rounded-md border border-loss/40 px-3 py-1.5 text-[13px] text-loss hover:bg-loss/[0.08]">
                        Supprimer l&apos;import
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <input type="search" value={query} onChange={(e) => { setQuery(e.target.value); setLimit(PAGE); }}
                     placeholder="Rechercher un titre" aria-label="Rechercher un titre"
                     className="min-w-[180px] flex-1 rounded-lg border border-line bg-ink px-3 py-2 text-sm text-text placeholder:text-faint focus:border-brass focus:outline-none" />
              <select value={type} onChange={(e) => { setType(e.target.value); setLimit(PAGE); }} aria-label="Type d'opération"
                      className="rounded-lg border border-line bg-ink px-3 py-2 text-sm text-text focus:border-brass focus:outline-none">
                <option value="">Tous les types</option>
                {Object.entries(TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
              {imports && imports.length > 0 && (
                <select value={importFilter} onChange={(e) => { setImportFilter(e.target.value); setLimit(PAGE); }} aria-label="Import d'origine"
                        className="max-w-[220px] rounded-lg border border-line bg-ink px-3 py-2 text-sm text-text focus:border-brass focus:outline-none">
                  <option value="">Tous les imports</option>
                  {imports.map((i) => <option key={i.id} value={i.id}>{i.file_path || "Import sans nom"}</option>)}
                  {orphanCount > 0 && <option value="__none">Sans import ({orphanCount})</option>}
                </select>
              )}
            </div>

            <div className="mb-2 flex min-h-[34px] flex-wrap items-center justify-between gap-2 text-[13px] text-muted">
              <span>{rows.length} opération(s) affichée(s){selected.size > 0 && <>, <span className="text-text">{selected.size} sélectionnée(s)</span></>}</span>
              {selected.size > 0 && (
                <button onClick={() => setConfirm({ kind: "selection" })}
                        className="rounded-md bg-loss/90 px-3 py-1.5 text-[13px] font-medium text-ink hover:bg-loss">
                  Supprimer la sélection
                </button>
              )}
            </div>

            <div className="overflow-x-auto rounded-lg border border-line">
              <table className="w-full text-[13px]">
                <thead className="text-left text-xs text-faint">
                  <tr>
                    <th className="w-10 px-3 py-2">
                      <input type="checkbox" checked={allVisibleSelected} aria-label="Tout sélectionner"
                             onChange={() => setSelected((s) => {
                               const n = new Set(s);
                               visible.forEach((r) => (allVisibleSelected ? n.delete(r.key) : n.add(r.key)));
                               return n;
                             })}
                             className="accent-[var(--color-brass)]" />
                    </th>
                    {["Date", "Opération", "Titre", "Quantité", "Prix", "Frais", "Montant", ""].map((h, j) => (
                      <th key={j} className={`whitespace-nowrap px-3 py-2 font-medium ${j >= 3 ? "text-right" : ""}`}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {visible.map(({ t, key }) => {
                    const total = t.amount ?? (t.quantity * t.price + (t.type === "sell" ? -t.fees : t.fees));
                    return (
                      <tr key={key} className={`border-t border-line ${selected.has(key) ? "bg-brass/[0.06]" : ""}`}>
                        <td className="px-3 py-2">
                          <input type="checkbox" checked={selected.has(key)} onChange={() => toggle(key)}
                                 aria-label={`Sélectionner ${t.name ?? t.symbol ?? "l'opération"} du ${formatDate(t.date)}`}
                                 className="accent-[var(--color-brass)]" />
                        </td>
                        <td className="whitespace-nowrap px-3 py-2">{formatDate(t.date)}</td>
                        <td className={`px-3 py-2 ${t.type === "sell" ? "text-loss" : t.type === "buy" ? "text-gain" : "text-muted"}`}>{TYPE_LABELS[t.type]}</td>
                        <td className="max-w-[240px] truncate px-3 py-2" title={t.name ?? t.symbol ?? ""}>{t.name ?? t.symbol ?? "—"}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{t.quantity ? formatCell(t.quantity) : "—"}</td>
                        <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">{t.price ? `${formatCell(t.price)} ${t.currency}` : "—"}</td>
                        <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">{t.fees ? `${formatCell(t.fees)} ${t.currency}` : "—"}</td>
                        <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">{total ? `${formatCell(total, "")} ${t.currency}` : "—"}</td>
                        <td className="px-2 py-1 text-right">
                          <button onClick={() => { setSelected(new Set([key])); setConfirm({ kind: "selection" }); }}
                                  aria-label="Supprimer cette opération" title="Supprimer cette opération"
                                  className="rounded-md p-1.5 text-faint hover:bg-loss/[0.1] hover:text-loss">
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                              <path d="M4 7h16M10 11v6M14 11v6M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2l1-12M9 7V4h6v3" />
                            </svg>
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                  {rows.length === 0 && (
                    <tr><td colSpan={9} className="px-3 py-10 text-center text-muted">Aucune opération ne correspond à ces filtres.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            {rows.length > limit && (
              <button onClick={() => setLimit((l) => l + PAGE)} className="mt-3 text-sm text-brass hover:underline">
                Afficher {Math.min(PAGE, rows.length - limit)} de plus ({rows.length - limit} restante(s))
              </button>
            )}
          </section>
        </div>

        {confirm && (
          <footer role="alertdialog" aria-labelledby="ops-confirm"
                  className="flex flex-wrap items-center justify-between gap-3 border-t border-loss/30 bg-loss/[0.07] px-6 py-4">
            <p id="ops-confirm" className="text-sm text-text">
              {confirm.kind === "import"
                ? <>Supprimer l&apos;import « {importToDelete?.file_path || "sans nom"} » et ses {importToDelete?.lines ?? 0} opération(s) ? Cette action est définitive.</>
                : <>Supprimer {selected.size} opération(s) ?{imports ? " Cette action est définitive." : ""}</>}
            </p>
            <div className="flex gap-2">
              <button onClick={() => setConfirm(null)} disabled={busy}
                      className="rounded-lg border border-line px-4 py-2 text-sm text-muted hover:border-faint hover:text-text">Annuler</button>
              <button disabled={busy}
                      onClick={() => run(async () => {
                        if (confirm.kind === "import") {
                          await onDeleteImport?.(confirm.id);
                          setImportFilter("");
                        } else {
                          await onDeleteTransactions([...selected]);
                        }
                      })}
                      className="rounded-lg bg-loss px-4 py-2 text-sm font-medium text-ink hover:opacity-90 disabled:opacity-50">
                {busy ? "Suppression…" : "Supprimer"}
              </button>
            </div>
          </footer>
        )}
      </div>
    </dialog>
  );
}
