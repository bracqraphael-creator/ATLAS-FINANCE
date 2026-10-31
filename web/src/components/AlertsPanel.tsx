"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { SupabaseClient } from "@supabase/supabase-js";
import {
  createAlert, deleteAlert, describe, KINDS, listAlerts, listEvents, runAlertsNow, setAlertActive,
  type AlertCondition, type AlertEvent, type AlertKind, type AlertRule,
} from "@/lib/alerts";
import { formatDate } from "@/lib/format";
import { DeviceCard } from "./AppDevice";

type Props = {
  open: boolean;
  onClose: () => void;
  supabase: SupabaseClient;
  portfolio: { id: string; name: string };
  lines: { symbol: string; name: string }[];   // lignes détenues, pour cibler une alerte
  email: string | null;
};

export function AlertsPanel({ open, onClose, supabase, portfolio, lines, email }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [kind, setKind] = useState<AlertKind>("line_move");
  const [symbol, setSymbol] = useState("");
  const [threshold, setThreshold] = useState("5");
  const [direction, setDirection] = useState<AlertCondition["direction"]>("below");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const spec = KINDS.find((k) => k.value === kind)!;
  const nameOf = useMemo(() => {
    const m = new Map(lines.map((l) => [l.symbol, l.name]));
    return (s: string) => m.get(s) ?? s;
  }, [lines]);

  const refresh = useCallback(async () => {
    try {
      const [r, e] = await Promise.all([listAlerts(supabase, portfolio.id), listEvents(supabase, portfolio.id)]);
      setRules(r); setEvents(e);
    } catch (err) { setError((err as Error).message); }
  }, [supabase, portfolio.id]);

  useEffect(() => {
    const d = dialog.current;
    if (!d) return;
    if (open && !d.open) { d.showModal(); refresh(); }
    if (!open && d.open) d.close();
    if (!open) { setError(null); setInfo(null); }
  }, [open, refresh]);

  const pickKind = (k: AlertKind) => {
    const s = KINDS.find((x) => x.value === k)!;
    setKind(k); setThreshold(String(s.defaults.threshold)); setDirection(s.defaults.direction);
    if (s.needsSymbol && !symbol && lines[0]) setSymbol(lines[0].symbol);
  };

  const act = async (fn: () => Promise<void>) => {
    setBusy(true); setError(null); setInfo(null);
    try { await fn(); await refresh(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };

  const add = () => act(async () => {
    const value = Number(threshold.replace(",", "."));
    if (!Number.isFinite(value) || value <= 0) throw new Error("Indiquez un seuil positif.");
    if (spec.needsSymbol && !symbol) throw new Error("Choisissez la ligne à surveiller.");
    await createAlert(supabase, portfolio.id, {
      kind, symbol: kind === "drawdown" ? null : symbol || null, threshold: value, direction,
    });
    setInfo("Alerte créée.");
  });

  const runNow = () => act(async () => {
    const r = await runAlertsNow(supabase);
    const parts = [r.new_events ? `${r.new_events} nouvelle(s) alerte(s) déclenchée(s)` : "Aucun nouveau franchissement de seuil sur les dernières clôtures"];
    if (r.new_events && r.emails_sent) parts.push(`e-mail envoyé à ${email ?? "votre adresse"}`);
    if (r.new_events && !r.email_configured) parts.push("envoi d'e-mails pas encore configuré");
    if (r.errors.length) parts.push(`${r.errors.length} erreur(s) : ${r.errors[0]}`);
    setInfo(parts.join(" ; ") + ".");
  });

  const unitLabel = spec.unit === "%" ? "%" : spec.unit === "cours" ? "dans la devise de cotation" : "sur 100";

  return (
    <dialog ref={dialog} onClose={onClose} aria-labelledby="alerts-title"
            className="m-auto w-[min(900px,calc(100vw-24px))] max-h-[calc(100vh-24px)] overflow-hidden rounded-2xl border border-line bg-panel p-0 text-text backdrop:bg-black/60 backdrop:backdrop-blur-[2px]">
      <div className="flex max-h-[calc(100vh-24px)] flex-col">
        <header className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
          <div>
            <h2 id="alerts-title" className="text-base font-semibold">Alertes de {portfolio.name}</h2>
            <p className="mt-0.5 text-[13px] text-muted">
              Vérification chaque matin du mardi au samedi, vers 7 h 30, sur les clôtures de la veille.
              {email ? ` E-mail à ${email}.` : ""}
            </p>
          </div>
          <button onClick={onClose} aria-label="Fermer" className="rounded-md px-2 py-1 text-muted hover:bg-panel-raised hover:text-text">✕</button>
        </header>

        <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-6 py-5">
          {error && <p role="alert" className="rounded-lg border border-loss/30 bg-loss/[0.08] px-4 py-3 text-sm text-loss">{error}</p>}
          {info && <p role="status" className="rounded-lg border border-gain/30 bg-gain/[0.07] px-4 py-3 text-sm text-gain">{info}</p>}

          <section className="rounded-xl border border-line p-4">
            <h3 className="mb-3 text-[13px] font-medium text-muted">Nouvelle alerte</h3>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="text-sm">
                <span className="mb-1 block text-xs text-faint">Type</span>
                <select value={kind} onChange={(e) => pickKind(e.target.value as AlertKind)}
                        className="w-full rounded-lg border border-line bg-ink px-3 py-2 text-sm text-text">
                  {KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
                </select>
              </label>
              {kind !== "drawdown" && (
                <label className="text-sm">
                  <span className="mb-1 block text-xs text-faint">Ligne</span>
                  <select value={symbol} onChange={(e) => setSymbol(e.target.value)}
                          className="w-full rounded-lg border border-line bg-ink px-3 py-2 text-sm text-text">
                    {!spec.needsSymbol && <option value="">Toutes les lignes détenues</option>}
                    {lines.map((l) => <option key={l.symbol} value={l.symbol}>{l.name}</option>)}
                  </select>
                </label>
              )}
              <label className="text-sm">
                <span className="mb-1 block text-xs text-faint">Seuil ({unitLabel})</span>
                <input inputMode="decimal" value={threshold} onChange={(e) => setThreshold(e.target.value)}
                       className="w-full rounded-lg border border-line bg-ink px-3 py-2 text-sm text-text" />
              </label>
              {spec.directions.length > 1 && (
                <label className="text-sm">
                  <span className="mb-1 block text-xs text-faint">Sens</span>
                  <select value={direction} onChange={(e) => setDirection(e.target.value as AlertCondition["direction"])}
                          className="w-full rounded-lg border border-line bg-ink px-3 py-2 text-sm text-text">
                    {spec.directions.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                  </select>
                </label>
              )}
            </div>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs text-faint">{spec.help} L&apos;alerte se déclenche quand le seuil est franchi, une seule fois.</p>
              <button onClick={add} disabled={busy}
                      className="rounded-lg bg-brass px-4 py-2 text-sm font-medium text-ink hover:opacity-90 disabled:opacity-50">
                Créer l&apos;alerte
              </button>
            </div>
          </section>

          <section>
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-[13px] font-medium text-muted">Alertes actives ({rules.filter((r) => r.active).length})</h3>
              {rules.length > 0 && (
                <button onClick={runNow} disabled={busy}
                        className="rounded-lg border border-line px-3 py-1.5 text-[13px] text-muted hover:border-faint hover:text-text disabled:opacity-50">
                  {busy ? "Vérification…" : "Vérifier maintenant"}
                </button>
              )}
            </div>
            {rules.length === 0 ? (
              <p className="rounded-lg border border-line px-4 py-6 text-center text-sm text-muted">Aucune alerte pour ce portefeuille.</p>
            ) : (
              <ul className="divide-y divide-line rounded-lg border border-line">
                {rules.map((r) => (
                  <li key={r.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                    <div className={`min-w-0 text-sm ${r.active ? "text-text" : "text-faint line-through"}`}>
                      {describe(r.condition, nameOf)}
                      {r.last_triggered_at && <div className="text-xs text-faint no-underline">Dernier déclenchement le {new Date(r.last_triggered_at).toLocaleDateString("fr-FR")}</div>}
                    </div>
                    <div className="flex gap-2">
                      <button onClick={() => act(() => setAlertActive(supabase, r.id, !r.active))} disabled={busy}
                              className="rounded-md border border-line px-3 py-1.5 text-[13px] text-muted hover:border-faint hover:text-text">
                        {r.active ? "Mettre en pause" : "Réactiver"}
                      </button>
                      <button onClick={() => act(() => deleteAlert(supabase, r.id))} disabled={busy}
                              className="rounded-md border border-loss/40 px-3 py-1.5 text-[13px] text-loss hover:bg-loss/[0.08]">
                        Supprimer
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h3 className="mb-2 text-[13px] font-medium text-muted">Historique</h3>
            {events.length === 0 ? (
              <p className="text-sm text-faint">Aucune alerte déclenchée pour l&apos;instant.</p>
            ) : (
              <ul className="space-y-2">
                {events.map((e) => (
                  <li key={e.id} className="rounded-lg border border-line px-4 py-2.5 text-sm">
                    <div className="text-xs text-faint">{formatDate(e.triggered_on)}{e.notified_at ? " · e-mail envoyé" : ""}</div>
                    <div className="text-text">{e.message}</div>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <DeviceCard supabase={supabase} />
          <p className="text-xs text-faint">Les alertes constatent le franchissement des seuils que vous fixez. Ceci n&apos;est pas un conseil en investissement.</p>
        </div>
      </div>
    </dialog>
  );
}
