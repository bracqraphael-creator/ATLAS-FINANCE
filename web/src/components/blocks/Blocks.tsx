import type { AllocationBlock, Block, Kpi, NoteBlock, TableBlock, TimeSeriesBlock } from "@/lib/types";
import { formatCell, formatDate, formatValue, toneOf } from "@/lib/format";
import { LineChart } from "./LineChart";

export function KpiCard({ kpi }: { kpi: Kpi }) {
  return (
    <div className="rounded-lg border border-border bg-surface px-4 py-3">
      <div className="text-xs text-muted">{kpi.label}</div>
      <div className={`mt-1 whitespace-nowrap text-lg font-semibold sm:text-xl ${toneOf(kpi.id, kpi.value)}`}>{formatValue(kpi.value, kpi.unit)}</div>
      {kpi.hint && <div className="mt-0.5 text-xs text-muted">{kpi.hint}</div>}
    </div>
  );
}

export function DataTable({ table }: { table: TableBlock }) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold">{table.title}</h3>
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-background text-left text-xs text-muted">
            <tr>
              {table.columns.map((c, j) => (
                <th key={c.key} className={`whitespace-nowrap px-3 py-2 font-medium ${j === 0 ? "" : "text-right"}`}>
                  {c.label}
                  {c.unit && c.unit !== "devise" ? ` (${c.unit === "EUR" ? "€" : c.unit})` : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, i) => (
              <tr key={i} className="border-t border-border">
                {table.columns.map((c, j) => {
                  const v = row[c.key];
                  const unit = c.unit === "EUR" ? "EUR" : "";
                  return (
                    <td key={c.key} className={`whitespace-nowrap px-3 py-2 ${j === 0 ? "font-medium" : "text-right"} ${typeof v === "number" ? toneOf(c.key, v) : ""}`}>
                      {typeof v === "number" ? formatCell(v, unit) : (v ?? "—")}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function AllocationBars({ block }: { block: AllocationBlock }) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold">{block.title}</h3>
      <ul className="space-y-1.5">
        {block.slices.map((s) => (
          <li key={s.label} className="text-sm">
            <div className="flex justify-between gap-2">
              <span className="truncate">{s.label}</span>
              <span className="text-muted">{formatValue(s.weight * 100, "%")}</span>
            </div>
            <div className="mt-0.5 h-1.5 rounded-full bg-background">
              <div className="h-1.5 rounded-full bg-accent" style={{ width: `${Math.max(s.weight * 100, 0.5)}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Note({ note }: { note: NoteBlock }) {
  const warn = note.level === "warning";
  return (
    <p className={`rounded-md px-3 py-2 text-xs ${warn ? "bg-warning/10 text-warning" : "bg-background text-muted"}`}>{note.text}</p>
  );
}

export function Series({ block }: { block: TimeSeriesBlock }) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold">{block.title}</h3>
      <LineChart series={block.series} unit={block.unit} />
    </div>
  );
}

/** Affiche n'importe quel résultat de module : les KPI en grille, puis les autres blocs. */
export function BlockList({ blocks, asOf }: { blocks: Block[]; asOf: string | null }) {
  const kpis = blocks.filter((b): b is Kpi => b.type === "kpi");
  const allocations = blocks.filter((b): b is AllocationBlock => b.type === "allocation");
  const rest = blocks.filter((b) => b.type !== "kpi" && b.type !== "allocation");
  return (
    <div className="space-y-5">
      {kpis.length > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {kpis.map((k) => <KpiCard key={k.id} kpi={k} />)}
        </div>
      )}
      {allocations.length > 0 && (
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {allocations.map((a) => <AllocationBars key={a.id} block={a} />)}
        </div>
      )}
      {rest.map((b) => {
        if (b.type === "table") return <DataTable key={b.id} table={b} />;
        if (b.type === "timeseries") return <Series key={b.id} block={b} />;
        if (b.type === "note") return <Note key={b.id} note={b} />;
        return null;
      })}
      <p className="text-xs text-muted">Données au {formatDate(asOf)}</p>
    </div>
  );
}
