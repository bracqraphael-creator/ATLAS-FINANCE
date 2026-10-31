// Miroir des modèles du moteur (engine/atlas/core/result.py et models.py).

export type Kpi = { type: "kpi"; id: string; label: string; value: number | null; unit: string; hint?: string | null };
export type TableBlock = {
  type: "table";
  id: string;
  title: string;
  columns: { key: string; label: string; unit?: string }[];
  rows: Record<string, string | number | null>[];
};
export type TimeSeriesBlock = {
  type: "timeseries";
  id: string;
  title: string;
  unit: string;
  series: { name: string; points: [string, number][] }[];
};
export type AllocationBlock = {
  type: "allocation";
  id: string;
  title: string;
  slices: { label: string; value: number; weight: number }[];
};
export type BarsBlock = { type: "bars"; id: string; title: string; unit: string; bars: { label: string; value: number }[] };
export type NoteBlock = { type: "note"; id: string; level: "info" | "warning"; text: string };
export type Block = Kpi | TableBlock | TimeSeriesBlock | AllocationBlock | BarsBlock | NoteBlock;

export type ModuleResult = {
  module_id: string;
  data_as_of: string | null;
  blocks: Block[];
  method: string;
  disclaimer: string;
};

export type ModuleParam = {
  key: string; label: string; type: string; unit?: string; default: number | null; min?: number; max?: number; step?: number;
};
export type ModuleManifest = {
  id: string;
  params?: ModuleParam[];
  name: string;
  family: string;
  priority: string;
  plan: string;
  texts: { title?: string; description?: string; method?: string };
};

export type Transaction = {
  id?: string;               // identifiant en base (portefeuille enregistré)
  importId?: string | null;  // import d'origine
  date: string;
  type: "buy" | "sell" | "dividend" | "fee" | "deposit" | "withdrawal" | "split";
  symbol: string | null;
  name: string | null;
  quantity: number;
  price: number;
  currency: string;
  fees: number;
  amount: number | null;
  account?: string | null;   // compte d'origine dans le fichier importé
};
export type AccountSummary = { label: string; wrapper: string; count: number; suggested_name: string };
/** Destination d'un compte du fichier : portefeuille existant ou nouveau portefeuille. */
export type AccountPlan = {
  label: string;
  count: number;
  destination: { kind: "existing"; id: string } | { kind: "new"; name: string; wrapper: string };
};
export type ImportResult = {
  format: string;
  format_label: string;
  transactions: Transaction[];
  instruments: Record<string, unknown>;
  rejected: { line: number; reason: string }[];
  notes: string[];
  accounts: AccountSummary[];
};
export type ImportAnalysis = {
  format: string;
  format_label: string;
  confidence: number;
  headers: string[];
  mapping: Record<string, number>;
  extras: Record<string, number>;
  fields: { key: string; label: string }[];
  missing: string[];
  sample: string[][];
  row_count: number;
};
