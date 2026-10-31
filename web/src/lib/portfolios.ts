// Accès aux portefeuilles enregistrés (Supabase). Chaque requête est filtrée par les politiques RLS :
// un utilisateur ne lit et n'écrit que ses propres lignes.
import type { SupabaseClient } from "@supabase/supabase-js";
import type { ImportResult, Transaction } from "./types";

export const WRAPPERS: { value: string; label: string }[] = [
  { value: "pea", label: "PEA" },
  { value: "pea_pme", label: "PEA-PME" },
  { value: "cto", label: "Compte-titres" },
  { value: "assurance_vie", label: "Assurance vie" },
  { value: "per", label: "PER" },
  { value: "crypto", label: "Crypto" },
  { value: "other", label: "Autre" },
];

export type Portfolio = { id: string; name: string; wrapper: string; broker: string | null; created_at: string };
export type Instrument = { symbol: string; name: string | null; asset_class: string; currency: string; country: string | null; sector: string | null };
export type PortfolioData = { transactions: Transaction[]; instruments: Record<string, Instrument>; importCount: number };

export async function listPortfolios(sb: SupabaseClient): Promise<Portfolio[]> {
  const { data, error } = await sb.from("portfolios").select("id, name, wrapper, broker, created_at").order("created_at");
  if (error) throw new Error("Impossible de charger vos portefeuilles.");
  return data ?? [];
}

export async function createPortfolio(sb: SupabaseClient, name: string, wrapper: string): Promise<Portfolio> {
  const { data: auth } = await sb.auth.getUser();
  if (!auth.user) throw new Error("Session expirée : reconnectez-vous.");
  const { data, error } = await sb.from("portfolios")
    .insert({ user_id: auth.user.id, name: name.trim(), wrapper })
    .select("id, name, wrapper, broker, created_at").single();
  if (error) throw new Error("Le portefeuille n'a pas pu être créé.");
  return data;
}

export async function deletePortfolio(sb: SupabaseClient, id: string): Promise<void> {
  const { error } = await sb.from("portfolios").delete().eq("id", id);
  if (error) throw new Error("Le portefeuille n'a pas pu être supprimé.");
}

type TxRow = {
  trade_date: string; type: Transaction["type"]; symbol: string | null; name: string | null;
  quantity: number | string; price: number | string; currency: string; fees: number | string; amount: number | string | null;
};

const num = (v: number | string | null) => (v === null ? null : Number(v));

export async function loadPortfolio(sb: SupabaseClient, id: string): Promise<PortfolioData> {
  const [tx, inst, imp] = await Promise.all([
    sb.from("transactions").select("trade_date, type, symbol, name, quantity, price, currency, fees, amount")
      .eq("portfolio_id", id).order("trade_date").limit(20000),
    sb.from("portfolio_instruments").select("symbol, name, asset_class, currency, country, sector").eq("portfolio_id", id),
    sb.from("imports").select("id", { count: "exact", head: true }).eq("portfolio_id", id),
  ]);
  if (tx.error || inst.error) throw new Error("Impossible de charger ce portefeuille.");
  const transactions = (tx.data as TxRow[]).map((r) => ({
    date: r.trade_date, type: r.type, symbol: r.symbol, name: r.name,
    quantity: Number(r.quantity), price: Number(r.price), currency: r.currency.trim(),
    fees: Number(r.fees), amount: num(r.amount),
  }));
  const instruments = Object.fromEntries((inst.data as Instrument[]).map((i) => [i.symbol, i]));
  return { transactions, instruments, importCount: imp.count ?? 0 };
}

/** Clé d'une opération, pour ne pas réenregistrer deux fois le même import. */
function fingerprint(t: Transaction): string {
  const r = (v: number | null) => (v === null ? "" : (Math.round(v * 1e6) / 1e6).toString());
  return [t.date, t.type, t.symbol ?? "", r(t.quantity), r(t.price), r(t.amount), t.currency].join("|");
}

export async function saveImport(
  sb: SupabaseClient, portfolioId: string, result: ImportResult, fileName: string, existing: Transaction[],
): Promise<{ inserted: number; duplicates: number }> {
  const { data: auth } = await sb.auth.getUser();
  if (!auth.user) throw new Error("Session expirée : reconnectez-vous.");
  const userId = auth.user.id;

  const seen = new Set(existing.map(fingerprint));
  const fresh = result.transactions.filter((t) => {
    const key = fingerprint(t);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  const { data: imp, error: impErr } = await sb.from("imports").insert({
    user_id: userId, portfolio_id: portfolioId, file_path: fileName, detected_format: result.format,
    rows_imported: fresh.length, rows_rejected: result.rejected, status: "done",
  }).select("id").single();
  if (impErr) throw new Error("L'import n'a pas pu être enregistré.");

  for (let i = 0; i < fresh.length; i += 500) {
    const chunk = fresh.slice(i, i + 500).map((t) => ({
      user_id: userId, portfolio_id: portfolioId, import_id: imp.id, trade_date: t.date, type: t.type,
      symbol: t.symbol, name: t.name, quantity: t.quantity, price: t.price, currency: t.currency,
      fees: t.fees, amount: t.amount,
    }));
    const { error } = await sb.from("transactions").insert(chunk);
    if (error) throw new Error("Une partie des opérations n'a pas pu être enregistrée. Réessayez l'import.");
  }

  const instruments = Object.values(result.instruments as Record<string, Instrument>).map((i) => ({
    portfolio_id: portfolioId, user_id: userId, symbol: i.symbol, name: i.name, asset_class: i.asset_class,
    currency: i.currency, country: i.country, sector: i.sector, updated_at: new Date().toISOString(),
  }));
  if (instruments.length) {
    // Les métadonnées déjà renseignées ne sont pas écrasées par un import qui n'en contient pas
    const { error } = await sb.from("portfolio_instruments").upsert(instruments, { onConflict: "portfolio_id,symbol", ignoreDuplicates: true });
    if (error) throw new Error("Les informations des titres n'ont pas pu être enregistrées.");
  }
  return { inserted: fresh.length, duplicates: result.transactions.length - fresh.length };
}
