import { useState } from "react";
import { View } from "react-native";
import { money } from "../../../shared/format";
import type { QuoteDraft } from "../../../shared/types";
import { C } from "../theme";
import { Banner, Group, Row, T } from "../ui";

export type CalcState = { status: "idle" | "loading" | "error"; message?: string };

const MATERIAL_KEYS = ["Paint", "Parts & materials", "Materials & sundries", "Surface preparation"];

function split(q: QuoteDraft) {
  const b = q.breakdown;
  const known = new Set([...MATERIAL_KEYS, "Labour", "Overheads & profit", "Call-out"]);
  const other = Object.entries(b).filter(([k]) => !known.has(k)).reduce((a, [, v]) => a + v, 0);
  return {
    labour: b.Labour ?? 0,
    materials: MATERIAL_KEYS.reduce((a, k) => a + (b[k] ?? 0), 0) + other,
    callout: b["Call-out"] ?? 0,
    overhead: b["Overheads & profit"] ?? 0,
  };
}

function Delta({ now, before, cur }: { now: number; before: number; cur: string }) {
  const d = Math.round((now - before) * 100) / 100;
  if (d === 0) return null;
  return <T v="foot" style={{ color: d > 0 ? C.ink : C.okInk, fontWeight: "600" }}>{d > 0 ? "+" : "−"}{money(Math.abs(d), cur).replace(/^\D+/, "")}</T>;
}

export function PriceCard({ quote, before, calc, durationHours }: { quote: QuoteDraft; before: QuoteDraft; calc: CalcState; durationHours: number | null }) {
  const [lines, setLines] = useState(false);
  const cur = quote.currency;
  const a = split(quote);
  const b = split(before);
  const busy = calc.status === "loading";

  const rows: [string, string | undefined, number, number][] = [
    ["Labour", quote.labor_hours != null ? `${quote.labor_hours} h` : undefined, a.labour, b.labour],
    ["Materials", undefined, a.materials, b.materials],
    ...(a.callout || b.callout ? ([["Call-out", undefined, a.callout, b.callout]] as [string, string | undefined, number, number][]) : []),
    ["Overheads and margin", undefined, a.overhead, b.overhead],
  ];

  return (
    <>
      <Group footer={durationHours != null ? `Estimated time on site: ${durationHours} h` : undefined}>
        {rows.map(([k, sub, v, was]) => (
          <Row
            key={k}
            title={k}
            subtitle={sub}
            right={
              <View style={{ alignItems: "flex-end", opacity: busy ? 0.5 : 1 }}>
                <T v="body" style={{ fontVariant: ["tabular-nums"] }}>{money(v, cur)}</T>
                <Delta now={v} before={was} cur={cur} />
              </View>
            }
          />
        ))}
        <Row
          title={<T v="headline">Total{busy ? "  recalculating…" : ""}</T>}
          right={
            <View style={{ alignItems: "flex-end", opacity: busy ? 0.5 : 1 }}>
              <T v="money">{money(quote.total, cur)}</T>
              <Delta now={quote.total ?? 0} before={before.total ?? 0} cur={cur} />
            </View>
          }
        />
        <Row title={lines ? "Hide line items" : "Show line items"} chevron={false} tint={C.blue} onPress={() => setLines((v) => !v)} />
      </Group>
      {calc.status === "error" ? <Banner text={calc.message ?? "Could not recalculate."} /> : null}
      {lines ? (
        <Group>
          {quote.lines.map((l, i) => (
            <Row key={i} title={l.description} subtitle={`${l.quantity} ${l.unit}`} right={<T v="sub" style={{ fontVariant: ["tabular-nums"] }}>{money(l.amount, cur)}</T>} />
          ))}
        </Group>
      ) : null}
    </>
  );
}
