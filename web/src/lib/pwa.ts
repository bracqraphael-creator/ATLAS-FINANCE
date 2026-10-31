// Application installable et notifications : enregistrement du service worker, invite d'installation, abonnement.
"use client";

import type { SupabaseClient } from "@supabase/supabase-js";
import { useEffect, useState } from "react";

type InstallPrompt = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };

export function registerServiceWorker() {
  if (typeof window === "undefined" || !("serviceWorker" in navigator)) return;
  navigator.serviceWorker.register("/sw.js").catch(() => { /* navigateur sans service worker : site normal */ });
}

/** Invite d'installation (Chrome, Edge, Android) ; sur iPhone l'installation passe par « Partager ». */
export function useInstall() {
  const [prompt, setPrompt] = useState<InstallPrompt | null>(null);
  const [installed, setInstalled] = useState(false);
  const [ios, setIos] = useState(false);
  useEffect(() => {
    setInstalled(window.matchMedia("(display-mode: standalone)").matches);
    setIos(/iphone|ipad|ipod/i.test(navigator.userAgent));
    const onPrompt = (e: Event) => { e.preventDefault(); setPrompt(e as InstallPrompt); };
    const onInstalled = () => setInstalled(true);
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => { window.removeEventListener("beforeinstallprompt", onPrompt); window.removeEventListener("appinstalled", onInstalled); };
  }, []);
  const install = async () => { if (!prompt) return; await prompt.prompt(); await prompt.userChoice; setPrompt(null); };
  return { canInstall: Boolean(prompt), install, installed, ios };
}

function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padded = (base64 + "=".repeat((4 - (base64.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
}

export function pushSupported(): boolean {
  return typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

export async function currentPushSubscription(): Promise<PushSubscription | null> {
  if (!pushSupported()) return null;
  const reg = await navigator.serviceWorker.ready;
  return reg.pushManager.getSubscription();
}

/** Abonne cet appareil : autorisation du navigateur, clé publique du serveur, enregistrement de l'abonnement. */
export async function enablePush(sb: SupabaseClient): Promise<void> {
  if (!pushSupported()) throw new Error("Ce navigateur ne gère pas les notifications. Sur iPhone, installez d'abord l'application (Partager → Sur l'écran d'accueil).");
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("Notifications refusées : autorisez-les dans les réglages du navigateur pour ce site.");
  const { data, error } = await sb.functions.invoke<{ publicKey: string }>("alerts-run", { body: { action: "vapid" } });
  if (error || !data?.publicKey) throw new Error("Le serveur de notifications ne répond pas. Réessayez dans un instant.");
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(data.publicKey) as BufferSource });
  const json = sub.toJSON() as { endpoint: string; keys: { p256dh: string; auth: string } };
  const { data: auth } = await sb.auth.getUser();
  if (!auth.user) throw new Error("Session expirée : reconnectez-vous.");
  const { error: saveError } = await sb.from("push_subscriptions").upsert({
    user_id: auth.user.id, endpoint: json.endpoint, p256dh: json.keys.p256dh, auth: json.keys.auth,
    user_agent: navigator.userAgent.slice(0, 200),
  }, { onConflict: "endpoint" });
  if (saveError) throw new Error("L'abonnement aux notifications n'a pas pu être enregistré.");
}

export async function disablePush(sb: SupabaseClient): Promise<void> {
  const sub = await currentPushSubscription();
  if (!sub) return;
  await sb.from("push_subscriptions").delete().eq("endpoint", sub.endpoint);
  await sub.unsubscribe();
}
