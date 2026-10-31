import type { AllocationBlock, BarsBlock, Block, Kpi, NoteBlock, TableBlock, TimeSeriesBlock } from "@/lib/types";
import { formatCell, formatDate, formatValue, toneOf } from "@/lib/format";
import { Donut, SLICE_COLORS } from "./Donut";
import { ColumnChart } from "./ColumnChart";
import { LineChart } from "./LineChart";

export function Panel({ title, children, className = "" }: { title?: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={`rounded-xl border border-line bg-panel ${className}`}>
      {title && <h3 className="border-b border-line px-5 py-3 text-[13px] font-medium text-muted">{title}</h3>}
      <div className="p-5">{children}</div>
    </section>
  );
}

/** Le chiffre principal du module, en grand, avec sa courbe. */
function Hero({ kpi, chart }: { kpi: Kpi; chart: TimeSeriesBlock }) {
  return (
    <section className="reveal rounded-xl border border-line bg-panel p-5 sm:p-6">
      <div className="mb-5">
        <div className="text-sm text-muted">{kpi.label}</div>
        <div className="mt-1 text-4xl font-semibold tracking-tight sm:text-5xl">{formatValue(kpi.value, kpi.unit)}</div>
      </div>
      <LineChart series={chart.series} unit={chart.unit} height={260} />
    </section>
  );
}

/** Bandeau d'indicateurs séparés par des filets, plutôt qu'une mosaïque de cartes. */
function KpiStrip({ kpis }: { kpis: Kpi[] }) {
  return (
    <div className="flex flex-wrap gap-px overflow-hidden rounded-xl border border-line bg-line">
      {kpis.map((k) => (
        <div key={k.id} className="min-w-[150px] flex-1 basis-[150px] bg-panel px-5 py-4">
          <div className="text-[13px] text-muted">{k.label}</div>
          <div className={`mt-1.5 whitespace-nowrap text-xl font-semibold tracking-tight ${toneOf(k.id, k.value)}`}>{formatValue(k.value, k.unit)}</div>
          {k.hint && <div className="mt-1 text-xs leading-snug text-faint">{k.hint}</div>}
        </div>
      ))}
    </div>
  );
}

export function DataTable({ table }: { table: TableBlock }) {
  // Colonnes de texte (nom de ligne, année…) alignées à gauche et tronquées ; chiffres et dates à droite
  const isText = (c: TableBlock["columns"][number]) =>
    !c.unit && table.rows.some((r) => typeof r[c.key] === "string") && !table.rows.some((r) => typeof r[c.key] === "number");
  return (
    <section className="overflow-hidden rounded-xl border border-line bg-panel">
      <h3 className="border-b border-line px-5 py-3 text-[13px] font-medium text-muted">{table.title}</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-faint">
              {table.columns.map((c) => (
                <th key={c.key} scope="col" className={`whitespace-nowrap px-5 py-2.5 font-medium ${isText(c) ? "" : "text-right"}`}>
                  {c.label}
                  {c.unit && c.unit !== "devise" && c.unit !== "date" ? ` (${c.unit === "EUR" ? "€" : c.unit})` : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, i) => (
              <tr key={i} className="border-t border-line transition-colors hover:bg-panel-raised">
                {table.columns.map((c, j) => {
                  const v = row[c.key];
                  const tone = typeof v === "number" ? toneOf(c.key, v) : "";
                  return (
                    <td key={c.key} title={isText(c) && typeof v === "string" ? v : undefined}
                        className={`whitespace-nowrap px-5 py-3 ${isText(c) ? `max-w-[280px] truncate ${j === 0 ? "font-medium" : ""} text-text`
                                                                          : `text-right tabular-nums ${tone || "text-text/90"}`}`}>
                      {typeof v === "number" ? formatCell(v, c.unit === "EUR" ? "EUR" : "")
                       : c.unit === "date" && typeof v === "string" ? formatDate(v) : (v ?? "—")}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Bars({ block }: { block: AllocationBlock }) {
  return (
    <ul className="space-y-3">
      {block.slices.map((s, i) => (
        <li key={s.label} className="text-sm">
          <div className="flex justify-between gap-3">
            <span className="truncate text-text">{s.label}</span>
            <span className="text-muted">{formatValue(s.weight * 100, "%")}</span>
          </div>
          <div className="mt-1.5 h-1 rounded-full bg-line">
            <div className="h-1 rounded-full" style={{ width: `${Math.max(s.weight * 100, 0.8)}%`, background: i === 0 ? SLICE_COLORS[0] : "var(--muted)" }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function Warning({ note }: { note: NoteBlock }) {
  return (
    <p className="rounded-lg border border-warn/30 bg-warn/[0.07] px-4 py-3 text-sm text-warn">{note.text}</p>
  );
}

/** Rendu générique d'un résultat de module. */
export function BlockList({ blocks, asOf }: { blocks: Block[]; asOf: string | null }) {
  const kpis = blocks.filter((b): b is Kpi => b.type === "kpi");
  const series = blocks.filter((b): b is TimeSeriesBlock => b.type === "timeseries");
  const allocations = blocks.filter((b): b is AllocationBlock => b.type === "allocation");
  const tables = blocks.filter((b): b is TableBlock => b.type === "table");
  const notes = blocks.filter((b): b is NoteBlock => b.type === "note");
  const bars = blocks.filter((b): b is BarsBlock => b.type === "bars");

  const heroChart = series.find((s) => s.id === "history");
  const hero = heroChart ? kpis[0] : undefined;
  const stripKpis = hero ? kpis.slice(1) : kpis;
  const otherSeries = series.filter((s) => s !== heroChart);
  const [mainAlloc, ...otherAllocs] = allocations;

  return (
    <div className="space-y-5">
      {notes.filter((n) => n.level === "warning").map((n) => <Warning key={n.id} note={n} />)}
      {hero && heroChart && <Hero kpi={hero} chart={heroChart} />}
      {stripKpis.length > 0 && <KpiStrip kpis={stripKpis} />}
      {bars.length > 0 && (
        <div className={`grid gap-5 ${bars.length > 1 ? "lg:grid-cols-2" : ""}`}>
          {bars.map((b) => <Panel key={b.id} title={b.title}><ColumnChart block={b} /></Panel>)}
        </div>
      )}

      {mainAlloc && (
        <div className="grid gap-5 lg:grid-cols-2">
          <Panel title={mainAlloc.title}><Donut block={mainAlloc} /></Panel>
          {otherAllocs.slice(0, 1).map((a) => <Panel key={a.id} title={a.title}><Bars block={a} /></Panel>)}
        </div>
      )}
      {otherAllocs.length > 1 && (
        <div className="grid gap-5 md:grid-cols-3">
          {otherAllocs.slice(1).map((a) => <Panel key={a.id} title={a.title}><Bars block={a} /></Panel>)}
        </div>
      )}

      {otherSeries.map((s) => (
        <Panel key={s.id} title={s.title}>
          <LineChart series={s.series} unit={s.unit} tone={s.id === "drawdown" ? "loss" : "brass"} />
        </Panel>
      ))}
      {tables.map((t) => <DataTable key={t.id} table={t} />)}

      <div className="space-y-1 text-xs text-faint">
        {notes.filter((n) => n.level !== "warning").map((n) => <p key={n.id}>{n.text}</p>)}
        <p>Données au {formatDate(asOf)}</p>
      </div>
    </div>
  );
}
