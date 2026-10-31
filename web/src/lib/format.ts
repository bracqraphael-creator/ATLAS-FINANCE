import type { Transaction } from "./types";

export const TYPE_LABELS: Record<Transaction["type"], string> = {
  buy: "Achat", sell: "Vente", dividend: "Dividende", fee: "Frais", deposit: "Versement", withdrawal: "Retrait", split: "Division",
};

const nf = (digits: number) => new Intl.NumberFormat("fr-FR", { minimumFractionDigits: digits, maximumFractionDigits: digits });

export function formatValue(value: number | string | null | undefined, unit = ""): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string") return value;
  if (unit === "EUR") return `${nf(2).format(value)} €`;
  if (unit === "%") return `${nf(2).format(value)} %`;
  if (Number.isInteger(value)) return nf(0).format(value);
  return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 4 }).format(value);
}

/** Libellé court pour les axes de graphique : « 27 k€ », « -15 % ». */
export function formatAxis(value: number, unit = ""): string {
  const compact = new Intl.NumberFormat("fr-FR", { notation: "compact", maximumFractionDigits: 1 }).format(value);
  if (unit === "EUR") return `${compact} €`;
  if (unit === "%") return `${compact} %`;
  return compact;
}

/** Nombre dans un tableau : 2 décimales au-delà de 1, jusqu'à 6 en dessous (crypto, fractions). */
export function formatCell(value: number, unit = ""): string {
  if (unit) return formatValue(value, unit);
  if (Number.isInteger(value)) return formatValue(value);
  const digits = Math.abs(value) >= 1 ? 2 : 6;
  return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: digits }).format(value);
}

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

/** Couleur sémantique pour les valeurs de performance (gain / perte). */
export function toneOf(id: string, value: number | null): string {
  if (value === null) return "";
  const signed = ["unrealized", "realized", "realized_year", "gains", "losses", "total_gain", "twr", "annualized", "irr", "ytd", "gain", "bench", "portfolio", "benchmark", "gap", "pnl", "pnl_pct", "annual_return", "max_drawdown", "worst_day", "best_day"];
  if (!signed.includes(id) || value === 0) return "";
  return value > 0 ? "text-gain" : "text-loss";
}
