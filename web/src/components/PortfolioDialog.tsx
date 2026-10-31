"use client";

import { useEffect, useRef, useState } from "react";
import { WRAPPERS } from "@/lib/portfolios";

type Props = { open: boolean; first: boolean; onClose: () => void; onCreate: (name: string, wrapper: string) => Promise<void> };

export function PortfolioDialog({ open, first, onClose, onCreate }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [name, setName] = useState("");
  const [wrapper, setWrapper] = useState("pea");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const d = dialog.current;
    if (!d) return;
    if (open && !d.open) { setName(""); setWrapper("pea"); setError(null); d.showModal(); }
    if (!open && d.open) d.close();
  }, [open]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) { setError("Donnez un nom à ce portefeuille."); return; }
    setBusy(true); setError(null);
    try { await onCreate(name, wrapper); onClose(); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  };

  return (
    <dialog ref={dialog} onClose={onClose} aria-labelledby="pf-title"
            className="m-auto w-[min(440px,calc(100vw-24px))] rounded-2xl border border-line bg-panel p-0 text-text backdrop:bg-black/60">
      <form onSubmit={submit} className="p-6">
        <h2 id="pf-title" className="text-base font-semibold">{first ? "Créer votre premier portefeuille" : "Nouveau portefeuille"}</h2>
        <p className="mt-1 text-sm text-muted">Un portefeuille par compte : un PEA, un compte-titres, une assurance vie… Vous pourrez en ajouter d&apos;autres.</p>
        <label className="mt-5 block text-sm">
          <span className="text-muted">Nom</span>
          <input autoFocus value={name} onChange={(e) => setName(e.target.value)} maxLength={60} placeholder="PEA Boursobank"
                 className="mt-1.5 w-full rounded-lg border border-line bg-ink px-3 py-2.5 text-text placeholder:text-faint focus:border-brass focus:outline-none" />
        </label>
        <label className="mt-4 block text-sm">
          <span className="text-muted">Type de compte</span>
          <select value={wrapper} onChange={(e) => setWrapper(e.target.value)}
                  className="mt-1.5 w-full rounded-lg border border-line bg-ink px-3 py-2.5 text-text focus:border-brass focus:outline-none">
            {WRAPPERS.map((w) => <option key={w.value} value={w.value}>{w.label}</option>)}
          </select>
        </label>
        {error && <p role="alert" className="mt-4 text-sm text-loss">{error}</p>}
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-lg border border-line px-4 py-2 text-sm text-muted hover:border-faint hover:text-text">Annuler</button>
          <button disabled={busy} className="rounded-lg bg-brass px-4 py-2 text-sm font-medium text-ink hover:opacity-90 disabled:opacity-50">
            {busy ? "Création…" : "Créer le portefeuille"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
