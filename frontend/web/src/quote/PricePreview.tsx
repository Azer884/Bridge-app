import { useState } from "react";
import { money } from "@shared/format";
import type { QuoteDraft } from "@shared/types";

export type CalcState = { status: "idle" | "loading" | "error"; message?: string };

const MATERIAL_KEYS = ["Paint", "Parts & materials", "Materials & sundries", "Surface preparation"];

function split(q: QuoteDraft) {
  const b = q.breakdown;
  const materials = MATERIAL_KEYS.reduce((s, k) => s + (b[k] ?? 0), 0);
  const known = new Set([...MATERIAL_KEYS, "Labour", "Overheads & profit", "Call-out"]);
  const other = Object.entries(b).filter(([k]) => !known.has(k)).reduce((s, [, v]) => s + v, 0);
  return { labour: b.Labour ?? 0, materials: materials + other, callout: b["Call-out"] ?? 0, overhead: b["Overheads & profit"] ?? 0 };
}

function Delta({ now, before, cur }: { now: number; before: number; cur: string }) {
  const d = Math.round((now - before) * 100) / 100;
  if (d === 0) return null;
  return <span className={`delta-chip ${d > 0 ? "up" : "down"}`}>{d > 0 ? "+" : "−"}{money(Math.abs(d), cur).replace(/^\D+/, "")}</span>;
}

export function PricePreview({ quote, before, calc, durationHours }: { quote: QuoteDraft; before: QuoteDraft; calc: CalcState; durationHours: number | null }) {
  const [lines, setLines] = useState(false);
  const cur = quote.currency;
  const a = split(quote);
  const b = split(before);
  const busy = calc.status === "loading";

  const rows: [string, string, number, number][] = [
    ["Labour", quote.labor_hours != null ? `${quote.labor_hours} h` : "", a.labour, b.labour],
    ["Materials", "", a.materials, b.materials],
    ...(a.callout || b.callout ? ([["Call-out", "", a.callout, b.callout]] as [string, string, number, number][]) : []),
    ["Overheads and margin", "", a.overhead, b.overhead],
  ];

  return (
    <div className={`price${busy ? " busy" : ""}`} aria-busy={busy}>
      <div className="price-rows">
        {rows.map(([k, sub, v, was]) => (
          <div key={k} className="price-row">
            <span>{k}{sub && <small className="num"> {sub}</small>}</span>
            <span className="num">
              <Delta now={v} before={was} cur={cur} />
              {money(v, cur)}
            </span>
          </div>
        ))}
        <div className="price-row total">
          <span>Total {busy && <small className="muted">recalculating…</small>}</span>
          <span className="num">
            <Delta now={quote.total ?? 0} before={before.total ?? 0} cur={cur} />
            {money(quote.total, cur)}
          </span>
        </div>
      </div>
      {durationHours != null && <p className="muted num">Estimated time on site: {durationHours} h</p>}
      {calc.status === "error" && <div className="alert" role="alert">{calc.message}</div>}
      <button type="button" className="link" onClick={() => setLines((v) => !v)} aria-expanded={lines}>
        {lines ? "Hide line items" : "Show line items"}
      </button>
      {lines && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Item</th><th className="r">Qty</th><th className="r">Amount</th></tr></thead>
            <tbody>
              {quote.lines.map((l, i) => (
                <tr key={i}><td>{l.description}</td><td className="r num">{l.quantity} {l.unit}</td><td className="r num">{money(l.amount, cur)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
