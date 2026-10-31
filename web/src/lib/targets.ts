// Répartition cible d'un portefeuille enregistré (module Rééquilibrage), protégée par RLS.
import type { SupabaseClient } from "@supabase/supabase-js";

export type Allocation = Record<string, number>;   // code -> poids en %

export async function loadTargets(sb: SupabaseClient, portfolioId: string): Promise<Allocation | null> {
  const { data, error } = await sb.from("targets").select("allocation").eq("portfolio_id", portfolioId).maybeSingle();
  if (error) throw new Error("Impossible de charger la répartition cible.");
  const a = (data?.allocation ?? null) as Allocation | null;
  return a && Object.keys(a).length ? a : null;
}

export async function saveTargets(sb: SupabaseClient, portfolioId: string, allocation: Allocation): Promise<void> {
  const { data: auth } = await sb.auth.getUser();
  if (!auth.user) throw new Error("Session expirée : reconnectez-vous.");
  const { error } = await sb.from("targets").upsert(
    { user_id: auth.user.id, portfolio_id: portfolioId, allocation, updated_at: new Date().toISOString() },
    { onConflict: "portfolio_id" });
  if (error) throw new Error("La répartition cible n'a pas pu être enregistrée.");
}
