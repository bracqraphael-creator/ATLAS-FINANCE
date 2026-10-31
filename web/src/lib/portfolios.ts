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
export type ImportRecord = { id: string; file_path: string | null; detected_format: string | null; created_at: string; lines: number };
export type PortfolioData = {
  transactions: Transaction[]; instruments: Record<string, Instrument>; imports: ImportRecord[]; importCount: number;
};

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
  id: string; import_id: string | null; account: string | null; trade_date: string; type: Transaction["type"]; symbol: string | null; name: string | null;
  quantity: number | string; price: number | string; currency: string; fees: number | string; amount: number | string | null;
};

const num = (v: number | string | null) => (v === null ? null : Number(v));

export async function loadPortfolio(sb: SupabaseClient, id: string): Promise<PortfolioData> {
  const [tx, inst, imp] = await Promise.all([
    sb.from("transactions").select("id, import_id, account, trade_date, type, symbol, name, quantity, price, currency, fees, amount")
      .eq("portfolio_id", id).order("trade_date").limit(20000),
    sb.from("portfolio_instruments").select("symbol, name, asset_class, currency, country, sector").eq("portfolio_id", id),
    sb.from("imports").select("id, file_path, detected_format, created_at").eq("portfolio_id", id).order("created_at"),
  ]);
  if (tx.error || inst.error || imp.error) throw new Error("Impossible de charger ce portefeuille.");
  const transactions = (tx.data as TxRow[]).map((r) => ({
    id: r.id, importId: r.import_id, account: r.account, date: r.trade_date, type: r.type, symbol: r.symbol, name: r.name,
    quantity: Number(r.quantity), price: Number(r.price), currency: r.currency.trim(),
    fees: Number(r.fees), amount: num(r.amount),
  }));
  const instruments = Object.fromEntries((inst.data as Instrument[]).map((i) => [i.symbol, i]));
  // Nombre de lignes encore présentes par import (certaines ont pu être supprimées une à une)
  const perImport = new Map<string, number>();
  for (const t of transactions) if (t.importId) perImport.set(t.importId, (perImport.get(t.importId) ?? 0) + 1);
  const imports = (imp.data as Omit<ImportRecord, "lines">[]).map((i) => ({ ...i, lines: perImport.get(i.id) ?? 0 }));
  return { transactions, instruments, imports, importCount: imports.length };
}

/** Supprime un import et, par cascade, toutes les opérations qu'il a créées. */
export async function deleteImport(sb: SupabaseClient, importId: string): Promise<void> {
  const { error } = await sb.from("imports").delete().eq("id", importId);
  if (error) throw new Error("L'import n'a pas pu être supprimé.");
}

/** Supprime des opérations précises (par lots, pour rester sous la limite de taille d'URL). */
export async function deleteTransactions(sb: SupabaseClient, ids: string[]): Promise<void> {
  for (let i = 0; i < ids.length; i += 200) {
    const { error } = await sb.from("transactions").delete().in("id", ids.slice(i, i + 200));
    if (error) throw new Error("Les opérations n'ont pas pu être supprimées.");
  }
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
      fees: t.fees, amount: t.amount, account: t.account ?? null,
    }));
    const { error } = await sb.from("transactions").insert(chunk);
    if (error) throw new Error("Une partie des opérations n'a pas pu être enregistrée. Réessayez l'import.");
  }

  const instruments = Object.values(result.instruments as Record<string, Instrument>).map((i) => ({
    portfolio_id: portfolioId, user_id: userId, symbol: i.symbol, name: i.name, asset_class: i.asset_class,
    currency: i.currency, country: i.country, sector: i.sector, updated_at: new Date().toISOString(),
  }));
  if (instruments.length) {
    // Le dernier import fait foi pour le nom, la classe d'actif et la devise (un import refait avec un lecteur
    // corrigé répare les fiches) ; pays et secteur déjà renseignés ne sont écrasés que si l'import en fournit.
    const withGeo = instruments.filter((i) => i.country || i.sector);
    const withoutGeo = instruments.filter((i) => !i.country && !i.sector).map((i) => ({
      portfolio_id: i.portfolio_id, user_id: i.user_id, symbol: i.symbol, name: i.name, asset_class: i.asset_class,
      currency: i.currency, updated_at: i.updated_at,
    }));
    for (const rows of [withGeo, withoutGeo]) {
      if (!rows.length) continue;
      const { error } = await sb.from("portfolio_instruments").upsert(rows, { onConflict: "portfolio_id,symbol" });
      if (error) throw new Error("Les informations des titres n'ont pas pu être enregistrées.");
    }
  }
  return { inserted: fresh.length, duplicates: result.transactions.length - fresh.length };
}

/** Nom affiché d'un compte du fichier : « Compte PEA » -> PEA, « Compte courant » (courtier en ligne) -> Compte-titres. */
export function accountLabel(account: string): string {
  const a = account.toLowerCase();
  if (/pea[\s-]*pme/.test(a)) return "PEA-PME";
  if (/\bpea\b/.test(a)) return "PEA";
  if (/assurance\s*vie/.test(a)) return "Assurance vie";
  if (/\bper\b/.test(a)) return "PER";
  if (/courant|titres|\bcto\b/.test(a)) return "Compte-titres";
  return account;
}
