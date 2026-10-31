// Alertes : règles par portefeuille et historique des déclenchements (Supabase, protégés par RLS).
import type { SupabaseClient } from "@supabase/supabase-js";
import { formatValue } from "./format";

export type AlertKind = "line_move" | "below_cost" | "price_cross" | "rsi" | "drawdown";
export type AlertCondition = { kind: AlertKind; symbol: string | null; threshold: number; direction: "above" | "below" | "both" };
export type AlertRule = { id: string; portfolio_id: string; condition: AlertCondition; active: boolean; last_triggered_at: string | null };
export type AlertEvent = { id: string; alert_id: string; triggered_on: string; message: string; notified_at: string | null; created_at: string };
export type RunSummary = { rules: number; new_events: number; emails_sent: number; email_configured: boolean; errors: string[] };

export const KINDS: { value: AlertKind; label: string; help: string; unit: "%" | "cours" | "niveau"; needsSymbol: boolean;
                      directions: { value: AlertCondition["direction"]; label: string }[]; defaults: { threshold: number; direction: AlertCondition["direction"] } }[] = [
  { value: "line_move", label: "Variation d'une séance", help: "Une ligne varie d'au moins X % entre deux clôtures.", unit: "%",
    needsSymbol: false, directions: [{ value: "below", label: "à la baisse" }, { value: "above", label: "à la hausse" }, { value: "both", label: "dans les deux sens" }],
    defaults: { threshold: 5, direction: "below" } },
  { value: "below_cost", label: "Sous le prix de revient", help: "Une ligne passe à X % ou plus sous votre prix de revient.", unit: "%",
    needsSymbol: false, directions: [{ value: "below", label: "à la baisse" }], defaults: { threshold: 10, direction: "below" } },
  { value: "price_cross", label: "Franchissement d'un cours", help: "Le cours d'une ligne franchit un niveau.", unit: "cours",
    needsSymbol: true, directions: [{ value: "above", label: "au-dessus" }, { value: "below", label: "en dessous" }, { value: "both", label: "dans les deux sens" }],
    defaults: { threshold: 100, direction: "above" } },
  { value: "rsi", label: "RSI 14 jours", help: "Le RSI d'une ligne franchit un niveau (souvent 70 ou 30).", unit: "niveau",
    needsSymbol: false, directions: [{ value: "above", label: "au-dessus" }, { value: "below", label: "en dessous" }],
    defaults: { threshold: 70, direction: "above" } },
  { value: "drawdown", label: "Baisse du portefeuille", help: "Le portefeuille recule d'au moins X % depuis son plus haut.", unit: "%",
    needsSymbol: false, directions: [{ value: "below", label: "à la baisse" }], defaults: { threshold: 10, direction: "below" } },
];

/** Phrase lisible : « Toutes les lignes : variation d'une séance d'au moins 5 % à la baisse ». */
export function describe(c: AlertCondition, nameOf: (s: string) => string): string {
  const k = KINDS.find((x) => x.value === c.kind);
  const who = c.kind === "drawdown" ? "Portefeuille" : c.symbol ? nameOf(c.symbol) : "Toutes les lignes";
  const dir = k?.directions.find((d) => d.value === c.direction)?.label ?? "";
  const t = c.kind === "price_cross" ? formatValue(c.threshold) : c.kind === "rsi" ? formatValue(c.threshold) : `${formatValue(c.threshold)} %`;
  switch (c.kind) {
    case "line_move": return `${who} : variation d'une séance d'au moins ${t} ${dir}`;
    case "below_cost": return `${who} : ${t} ou plus sous le prix de revient`;
    case "price_cross": return `${who} : cours ${dir} de ${t}`;
    case "rsi": return `${who} : RSI 14 jours ${dir} de ${t}`;
    case "drawdown": return `${who} : baisse d'au moins ${t} depuis le plus haut`;
  }
}

export async function listAlerts(sb: SupabaseClient, portfolioId: string): Promise<AlertRule[]> {
  const { data, error } = await sb.from("alerts").select("id, portfolio_id, condition, active, last_triggered_at")
    .eq("portfolio_id", portfolioId).order("created_at");
  if (error) throw new Error("Impossible de charger les alertes.");
  return data as AlertRule[];
}

export async function createAlert(sb: SupabaseClient, portfolioId: string, condition: AlertCondition): Promise<void> {
  const { data: auth } = await sb.auth.getUser();
  if (!auth.user) throw new Error("Session expirée : reconnectez-vous.");
  const { error } = await sb.from("alerts").insert({ user_id: auth.user.id, portfolio_id: portfolioId, condition, channels: ["email"] });
  if (error) throw new Error("L'alerte n'a pas pu être créée.");
}

export async function setAlertActive(sb: SupabaseClient, id: string, active: boolean): Promise<void> {
  const { error } = await sb.from("alerts").update({ active }).eq("id", id);
  if (error) throw new Error("L'alerte n'a pas pu être modifiée.");
}

export async function deleteAlert(sb: SupabaseClient, id: string): Promise<void> {
  const { error } = await sb.from("alerts").delete().eq("id", id);
  if (error) throw new Error("L'alerte n'a pas pu être supprimée.");
}

export async function listEvents(sb: SupabaseClient, portfolioId: string): Promise<AlertEvent[]> {
  const { data, error } = await sb.from("alert_events").select("id, alert_id, triggered_on, message, notified_at, created_at")
    .eq("portfolio_id", portfolioId).order("created_at", { ascending: false }).limit(50);
  if (error) throw new Error("Impossible de charger l'historique des alertes.");
  return data as AlertEvent[];
}

/** Évalue tout de suite les alertes de l'utilisateur connecté (même traitement que la vérification du matin). */
export async function runAlertsNow(sb: SupabaseClient): Promise<RunSummary> {
  const { data, error } = await sb.functions.invoke<RunSummary>("alerts-run", { body: {} });
  if (error || !data) throw new Error("La vérification n'a pas pu être lancée. Réessayez dans un instant.");
  return data;
}
