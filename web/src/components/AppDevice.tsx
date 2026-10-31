"use client";

import { useEffect, useState } from "react";
import type { SupabaseClient } from "@supabase/supabase-js";
import { currentPushSubscription, disablePush, enablePush, pushSupported, useInstall } from "@/lib/pwa";

/** Installation de l'application sur l'appareil (bouton compact pour la navigation). */
export function InstallButton({ className = "" }: { className?: string }) {
  const { canInstall, install, installed } = useInstall();
  if (installed || !canInstall) return null;
  return (
    <button onClick={install} className={`rounded-lg border border-brass/40 px-3 py-2 text-sm text-brass hover:bg-brass/[0.08] ${className}`}>
      Installer l&apos;application
    </button>
  );
}

/** Carte « Application et notifications » : installation et abonnement de cet appareil aux alertes. */
export function DeviceCard({ supabase }: { supabase: SupabaseClient }) {
  const { canInstall, install, installed, ios } = useInstall();
  const [subscribed, setSubscribed] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => { currentPushSubscription().then((s) => setSubscribed(Boolean(s))).catch(() => setSubscribed(false)); }, []);

  const toggle = async () => {
    setBusy(true); setMessage(null);
    try {
      if (subscribed) { await disablePush(supabase); setSubscribed(false); setMessage({ ok: true, text: "Notifications désactivées sur cet appareil." }); }
      else { await enablePush(supabase); setSubscribed(true); setMessage({ ok: true, text: "Notifications activées : les alertes arriveront aussi sur cet appareil." }); }
    } catch (e) { setMessage({ ok: false, text: (e as Error).message }); }
    finally { setBusy(false); }
  };

  return (
    <section className="rounded-xl border border-line bg-panel p-5">
      <h2 className="text-sm font-semibold">Application et notifications</h2>
      <div className="mt-3 space-y-3 text-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="text-muted">
            {installed ? "Application installée sur cet appareil."
             : ios ? "Sur iPhone : bouton Partager, puis « Sur l'écran d'accueil »."
             : canInstall ? "Ajoutez ATLAS à l'écran d'accueil de cet appareil."
             : "Installation : menu du navigateur, « Installer l'application » ou « Ajouter à l'écran d'accueil »."}
          </span>
          {canInstall && !installed && (
            <button onClick={install} className="rounded-lg bg-brass px-4 py-2 text-sm font-medium text-ink hover:opacity-90">Installer</button>
          )}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3">
          <span className="text-muted">
            {!pushSupported() ? "Notifications non disponibles dans ce navigateur" + (ios ? " : installez d'abord l'application." : ".")
             : subscribed ? "Les alertes arrivent en notification sur cet appareil." : "Recevoir les alertes en notification sur cet appareil."}
          </span>
          {pushSupported() && subscribed !== null && (
            <button onClick={toggle} disabled={busy}
                    className="rounded-lg border border-line px-4 py-2 text-sm text-text hover:border-faint disabled:opacity-50">
              {busy ? "…" : subscribed ? "Désactiver" : "Activer les notifications"}
            </button>
          )}
        </div>
        {message && <p className={`text-xs ${message.ok ? "text-gain" : "text-loss"}`}>{message.text}</p>}
      </div>
    </section>
  );
}
