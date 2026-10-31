"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { AccountPlan, ImportAnalysis, ImportResult } from "@/lib/types";
import { WRAPPERS } from "@/lib/portfolios";
import { formatCell, formatDate, TYPE_LABELS } from "@/lib/format";
const REQUIRED = new Set(["date"]);
// v2 : les correspondances enregistrées avant l'ajout de la colonne « Compte » sont ignorées
const STORAGE_PREFIX = "atlas-mapping-v2:";
// Formats reconnus par un lecteur dédié : leur correspondance est toujours celle du moteur, jamais une mémoire
const BUILT_IN = (format: string) => format.startsWith("pdf-") || ["degiro", "atlas-standard"].includes(format);

type PortfolioRef = { id: string; name: string; wrapper: string };
type Props = {
  open: boolean;
  onClose: () => void;
  onImported: (result: ImportResult, fileName: string, plan?: AccountPlan[]) => void;
  target?: string | null;
  /** Portefeuilles de l'utilisateur connecté : chaque compte du fichier peut aller dans le sien. */
  portfolios?: PortfolioRef[];
  currentId?: string | null;
  currentEmpty?: boolean;
};

/** Destination proposée pour chaque compte : portefeuille du même nom (réimport), sinon le portefeuille courant
 *  s'il est vide et de la même enveloppe, sinon un nouveau portefeuille. */
function defaultPlan(result: ImportResult, portfolios: PortfolioRef[], currentId?: string | null, currentEmpty?: boolean): AccountPlan[] {
  let currentUsed = false;
  return result.accounts.map((a) => {
    const same = portfolios.find((p) => p.name.trim().toLowerCase() === a.suggested_name.trim().toLowerCase());
    if (same) return { label: a.label, count: a.count, destination: { kind: "existing", id: same.id } };
    const current = portfolios.find((p) => p.id === currentId);
    if (current && currentEmpty && !currentUsed && current.wrapper === a.wrapper) {
      currentUsed = true;
      return { label: a.label, count: a.count, destination: { kind: "existing", id: current.id } };
    }
    return { label: a.label, count: a.count, destination: { kind: "new", name: a.suggested_name, wrapper: a.wrapper } };
  });
}

async function post<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`/api/engine/${path}`, { method: "POST", body: form });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail ?? `Erreur ${res.status}`);
  return body as T;
}

// Correspondances mémorisées par navigateur, reconnues à la signature des en-têtes.
function signature(headers: string[]) { return STORAGE_PREFIX + headers.join("|").slice(0, 400); }
function loadMapping(headers: string[]): Record<string, number> | null {
  try { const v = localStorage.getItem(signature(headers)); return v ? JSON.parse(v) : null; } catch { return null; }
}
function saveMapping(headers: string[], mapping: Record<string, number>) {
  try { localStorage.setItem(signature(headers), JSON.stringify(mapping)); } catch { /* stockage indisponible */ }
}

export function ImportWizard({ open, onClose, onImported, target, portfolios, currentId, currentEmpty }: Props) {
  const [plan, setPlan] = useState<AccountPlan[]>([]);
  // Par défaut, les comptes d'un fichier restent ensemble, ventilés comme dans l'application du courtier
  const [split, setSplit] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<ImportAnalysis | null>(null);
  const [mapping, setMapping] = useState<Record<string, number>>({});
  const [remembered, setRemembered] = useState(false);
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);

  const reset = useCallback(() => {
    setFile(null); setAnalysis(null); setMapping({}); setPreview(null); setError(null); setRemembered(false); setPlan([]); setSplit(false);
  }, []);

  useEffect(() => {
    const d = dialog.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) { d.close(); reset(); }
  }, [open, reset]);

  const analyze = async (f: File) => {
    setBusy(true); setError(null); setFile(f);
    try {
      const form = new FormData();
      form.append("file", f);
      const a = await post<ImportAnalysis>("imports/analyze", form);
      // Mémoire utilisée seulement pour les formats génériques, et complétée par les colonnes nouvellement reconnues
      const saved = BUILT_IN(a.format) ? null : loadMapping(a.headers);
      const valid = saved ? Object.fromEntries(Object.entries(saved).filter(([, i]) => i < a.headers.length)) : null;
      setAnalysis(a);
      setMapping(valid ? { ...a.mapping, ...valid } : a.mapping);
      setRemembered(Boolean(valid));
    } catch (e) {
      setError((e as Error).message); setFile(null);
    } finally {
      setBusy(false);
    }
  };

  // Aperçu recalculé à chaque changement de correspondance
  useEffect(() => {
    if (!file || !analysis) return;
    const handle = setTimeout(async () => {
      const form = new FormData();
      form.append("file", file);
      const custom = JSON.stringify(mapping) !== JSON.stringify(analysis.mapping);
      if (custom) form.append("mapping", JSON.stringify(mapping));
      if (custom && Object.keys(analysis.extras).length) form.append("extras", JSON.stringify(analysis.extras));
      try {
        const result = await post<ImportResult>("imports", form);
        setPreview(result);
        setPlan((old) => {
          // Les choix déjà faits pour les mêmes comptes sont conservés quand la correspondance change
          const fresh = defaultPlan(result, portfolios ?? [], currentId, currentEmpty);
          return fresh.map((p) => ({ ...p, destination: old.find((o) => o.label === p.label)?.destination ?? p.destination }));
        });
        setError(null);
      }
      catch (e) { setError((e as Error).message); }
    }, 250);
    return () => clearTimeout(handle);
  }, [file, analysis, mapping, portfolios, currentId, currentEmpty]);

  const confirm = () => {
    if (!preview || !analysis || !file) return;
    // On ne retient que les corrections faites à la main, et jamais pour un format à lecteur dédié
    if (!BUILT_IN(analysis.format) && JSON.stringify(mapping) !== JSON.stringify(analysis.mapping)) saveMapping(analysis.headers, mapping);
    const multi = preview.accounts.length > 1 && portfolios && split;
    onImported(preview, file.name, multi ? plan : undefined);
    onClose();
  };

  const columnLabel = (i: number) => {
    const h = analysis?.headers[i]?.trim();
    const ex = analysis?.sample.find((r) => r[i]?.trim())?.[i]?.trim();
    const base = h || `Colonne ${i + 1}`;
    return ex ? `${base} (ex. ${ex.slice(0, 24)})` : base;
  };

  const count = preview?.transactions.length ?? 0;
  const blocked = !mapping.date && mapping.date !== 0;

  return (
    <dialog ref={dialog} onClose={onClose} aria-labelledby="import-title"
            className="m-auto w-[min(1080px,calc(100vw-24px))] max-h-[calc(100vh-24px)] overflow-hidden rounded-2xl border border-line bg-panel p-0 text-text backdrop:bg-black/60 backdrop:backdrop-blur-[2px]">
      <div className="flex max-h-[calc(100vh-24px)] flex-col">
        <header className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
          <div>
            <h2 id="import-title" className="text-base font-semibold">{target ? `Importer dans ${target}` : "Importer des opérations"}</h2>
            <p className="mt-0.5 text-[13px] text-muted">
              {analysis ? `${file?.name}, ${analysis.row_count} ligne(s) lue(s)` : "Export CSV, Excel ou PDF de votre courtier, de votre banque ou d'un autre logiciel"}
            </p>
          </div>
          <button onClick={onClose} className="rounded-md px-2 py-1 text-muted hover:bg-panel-raised hover:text-text" aria-label="Fermer">✕</button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          {error && <p role="alert" className="mb-4 rounded-lg border border-loss/30 bg-loss/[0.08] px-4 py-3 text-sm text-loss">{error}</p>}

          {!analysis && (
            <div
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files?.[0]; if (f) analyze(f); }}
              className={`flex flex-col items-center justify-center rounded-xl border border-dashed px-6 py-14 text-center transition-colors ${
                dragging ? "border-brass bg-brass/[0.06]" : "border-line"}`}>
              <p className="text-[15px] font-medium">{busy ? "Analyse du fichier…" : "Déposez votre fichier ici"}</p>
              <p className="mt-1 text-sm text-muted">CSV, Excel ou PDF, 5 Mo maximum</p>
              <button onClick={() => input.current?.click()} disabled={busy}
                      className="mt-5 rounded-lg bg-brass px-4 py-2 text-sm font-medium text-ink hover:opacity-90 disabled:opacity-50">
                Choisir un fichier
              </button>
              <input ref={input} type="file" accept=".csv,.txt,.xlsx,.xlsm,.pdf,text/csv,application/pdf" className="sr-only"
                     onChange={(e) => { const f = e.target.files?.[0]; if (f) analyze(f); e.target.value = ""; }} />
              <ul className="mt-8 max-w-[60ch] space-y-1 text-left text-[13px] text-muted">
                <li>DEGIRO (export « Transactions ») est reconnu automatiquement.</li>
                <li>PDF acceptés : historique d&apos;opérations en tableau, avis d&apos;opéré, relevé de portefeuille. Les PDF scannés (images) ne sont pas lisibles.</li>
                <li>Pour les autres courtiers, banques et logiciels, les colonnes sont devinées : vous vérifiez la correspondance avant d&apos;importer.</li>
                <li>Une fois validée, la correspondance est mémorisée pour vos prochains imports du même format.</li>
              </ul>
            </div>
          )}

          {analysis && (
            <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
              <section>
                <div className="mb-4 rounded-lg border border-line bg-ink/40 px-4 py-3">
                  <div className="text-sm font-medium">{remembered ? "Correspondance mémorisée" : analysis.format_label}</div>
                  <div className="mt-0.5 text-xs text-muted">
                    {remembered ? "Celle que vous avez validée pour ce format." :
                     analysis.confidence >= 0.8 ? "Colonnes reconnues avec confiance. Vérifiez l'aperçu." :
                     "Certaines colonnes sont à confirmer ci-dessous."}
                  </div>
                </div>
                <h3 className="mb-2 text-[13px] font-medium text-muted">Correspondance des colonnes</h3>
                <div className="space-y-2">
                  {analysis.fields.map((f) => (
                    <label key={f.key} className="grid grid-cols-[120px_1fr] items-center gap-3 text-sm">
                      <span className={mapping[f.key] === undefined ? "text-faint" : "text-text"}>
                        {f.label}{REQUIRED.has(f.key) && <span className="text-brass"> *</span>}
                      </span>
                      <select value={mapping[f.key] ?? ""}
                              onChange={(e) => {
                                const v = e.target.value;
                                setRemembered(false);
                                setMapping((m) => { const n = { ...m }; if (v === "") delete n[f.key]; else n[f.key] = Number(v); return n; });
                              }}
                              className="min-w-0 truncate rounded-md border border-line bg-ink px-2 py-1.5 text-[13px] text-text">
                        <option value="">Ignorer</option>
                        {analysis.headers.map((_, i) => <option key={i} value={i}>{columnLabel(i)}</option>)}
                      </select>
                    </label>
                  ))}
                </div>
                <p className="mt-3 text-xs leading-relaxed text-faint">
                  Sans colonne de type, l&apos;opération est déduite du libellé ou du signe de la quantité. Sans symbole, le code ISIN ou le nom du titre est utilisé.
                </p>
              </section>

              <section className="min-w-0">
                {preview && preview.accounts.length > 1 && (
                  <div className="mb-4 rounded-lg border border-brass/30 bg-brass/[0.06] p-4">
                    <h3 className="text-sm font-medium text-text">{preview.accounts.length} comptes détectés dans ce fichier</h3>
                    {portfolios ? (
                      <>
                        <div className="mt-2 space-y-1.5 text-[13px]">
                          <label className="flex items-start gap-2">
                            <input type="radio" name="split" checked={!split} onChange={() => setSplit(false)} className="mt-0.5 accent-[var(--color-brass)]" />
                            <span><span className="text-text">Un seul portefeuille{target ? ` (${target})` : ""}, ventilé par compte</span>
                              <span className="block text-xs text-faint">Comme dans l&apos;application du courtier : un menu permet d&apos;afficher chaque compte.</span></span>
                          </label>
                          <label className="flex items-start gap-2">
                            <input type="radio" name="split" checked={split} onChange={() => setSplit(true)} className="mt-0.5 accent-[var(--color-brass)]" />
                            <span className="text-text">Un portefeuille par compte</span>
                          </label>
                        </div>
                        {!split && (
                          <p className="mt-2 text-xs text-muted">{preview.accounts.map((a) => `${a.label} (${a.count})`).join(", ")}</p>
                        )}
                        {split && <div className="mt-3 space-y-2">
                          {plan.map((p, k) => {
                            const dest = p.destination;
                            const update = (d: AccountPlan["destination"]) =>
                              setPlan((all) => all.map((x, j) => (j === k ? { ...x, destination: d } : x)));
                            return (
                              <div key={p.label} className="grid items-center gap-2 text-[13px] sm:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_minmax(0,1fr)]">
                                <div className="min-w-0">
                                  <div className="truncate text-text">{p.label}</div>
                                  <div className="text-xs text-faint">{p.count} opération(s)</div>
                                </div>
                                <select aria-label={`Destination de ${p.label}`}
                                        value={dest.kind === "existing" ? dest.id : "__new"}
                                        onChange={(e) => {
                                          const v = e.target.value;
                                          const acc = preview.accounts.find((a) => a.label === p.label);
                                          update(v === "__new" ? { kind: "new", name: acc?.suggested_name ?? p.label, wrapper: acc?.wrapper ?? "other" }
                                                               : { kind: "existing", id: v });
                                        }}
                                        className="min-w-0 rounded-md border border-line bg-ink px-2 py-1.5 text-text">
                                  <option value="__new">Nouveau portefeuille</option>
                                  {portfolios.map((pf) => <option key={pf.id} value={pf.id}>{pf.name}</option>)}
                                </select>
                                {dest.kind === "new" ? (
                                  <div className="flex min-w-0 gap-2">
                                    <input value={dest.name} aria-label={`Nom du portefeuille pour ${p.label}`}
                                           onChange={(e) => update({ ...dest, name: e.target.value })}
                                           className="min-w-0 flex-1 rounded-md border border-line bg-ink px-2 py-1.5 text-text" />
                                    <select value={dest.wrapper} aria-label={`Enveloppe de ${p.label}`}
                                            onChange={(e) => update({ ...dest, wrapper: e.target.value })}
                                            className="rounded-md border border-line bg-ink px-2 py-1.5 text-text">
                                      {WRAPPERS.map((w) => <option key={w.value} value={w.value}>{w.label}</option>)}
                                    </select>
                                  </div>
                                ) : <span className="text-xs text-faint">Ajouté au portefeuille existant (doublons ignorés)</span>}
                              </div>
                            );
                          })}
                        </div>}
                      </>
                    ) : (
                      <p className="mt-0.5 text-xs text-muted">
                        {preview.accounts.map((a) => `${a.label} (${a.count})`).join(", ")}. Vous pourrez afficher chaque compte séparément ; connectez-vous pour les enregistrer chacun dans un portefeuille.
                      </p>
                    )}
                  </div>
                )}
                <div className="mb-2 flex items-baseline justify-between gap-3">
                  <h3 className="text-[13px] font-medium text-muted">Aperçu</h3>
                  {preview && (
                    <span className="text-[13px] text-muted">
                      <span className="text-text">{count}</span> opération(s) prête(s)
                      {preview.rejected.length > 0 && <>, <span className="text-warn">{preview.rejected.length} ignorée(s)</span></>}
                    </span>
                  )}
                </div>
                <div className="overflow-x-auto rounded-lg border border-line">
                  <table className="w-full text-[13px]">
                    <thead className="text-left text-xs text-faint">
                      <tr>{["Date", "Opération", "Titre", "Quantité", "Prix", "Frais / montant"].map((h, j) => (
                        <th key={h} className={`whitespace-nowrap px-3 py-2 font-medium ${j >= 3 ? "text-right" : ""}`}>{h}</th>))}</tr>
                    </thead>
                    <tbody>
                      {(preview?.transactions ?? []).slice(0, 12).map((t, i) => (
                        <tr key={i} className="border-t border-line">
                          <td className="whitespace-nowrap px-3 py-2">{formatDate(t.date)}</td>
                          <td className={`px-3 py-2 ${t.type === "sell" ? "text-loss" : t.type === "buy" ? "text-gain" : "text-muted"}`}>{TYPE_LABELS[t.type]}</td>
                          <td className="max-w-[200px] truncate px-3 py-2" title={t.name ?? t.symbol ?? ""}>{t.name ?? t.symbol ?? "—"}</td>
                          <td className="px-3 py-2 text-right">{t.quantity ? formatCell(t.quantity) : "—"}</td>
                          <td className="whitespace-nowrap px-3 py-2 text-right">{t.price ? `${formatCell(t.price)} ${t.currency}` : "—"}</td>
                          <td className="whitespace-nowrap px-3 py-2 text-right">{t.amount !== null ? `${formatCell(t.amount)} ${t.currency}` : t.fees ? `${formatCell(t.fees)} ${t.currency}` : "—"}</td>
                        </tr>
                      ))}
                      {preview && count === 0 && (
                        <tr><td colSpan={6} className="px-3 py-8 text-center text-muted">Aucune opération lisible avec cette correspondance.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
                {count > 12 && <p className="mt-1.5 text-xs text-faint">… et {count - 12} autre(s).</p>}
                {preview?.notes.map((n) => <p key={n} className="mt-2 text-xs text-muted">{n}</p>)}
                {preview && preview.rejected.length > 0 && (
                  <details className="mt-3 rounded-lg border border-warn/30 bg-warn/[0.07] px-4 py-2.5 text-[13px] text-warn">
                    <summary className="cursor-pointer">Lignes ignorées et raison</summary>
                    <ul className="mt-2 max-h-40 space-y-0.5 overflow-y-auto">
                      {preview.rejected.slice(0, 50).map((r) => <li key={r.line}>Ligne {r.line} : {r.reason}</li>)}
                    </ul>
                  </details>
                )}
              </section>
            </div>
          )}
        </div>

        <footer className="flex items-center justify-between gap-3 border-t border-line px-6 py-4">
          {analysis ? (
            <button onClick={reset} className="text-sm text-muted hover:text-text">Changer de fichier</button>
          ) : <span />}
          <div className="flex gap-2">
            <button onClick={onClose} className="rounded-lg border border-line px-4 py-2 text-sm text-muted hover:border-faint hover:text-text">Annuler</button>
            {analysis && (
              <button onClick={confirm} disabled={!count || blocked}
                      className="rounded-lg bg-brass px-4 py-2 text-sm font-medium text-ink hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40">
                Importer {count} opération{count > 1 ? "s" : ""}{preview && preview.accounts.length > 1 && portfolios && split ? ` dans ${preview.accounts.length} portefeuilles` : ""}
              </button>
            )}
          </div>
        </footer>
      </div>
    </dialog>
  );
}
