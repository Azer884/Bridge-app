import { View } from "react-native";
import type { AuditActor, AuditEntry } from "../../../shared/types";
import { C } from "../theme";
import { Group, Row, T } from "../ui";

const ACTOR: Record<AuditActor, string> = { customer: "Customer", ai: "Gesir AI", system: "System", owner: "You" };
const dot = (a: AuditActor) => (a === "owner" ? C.blue : a === "ai" ? C.ok : a === "customer" ? C.tape : C.ink3);
const when = (iso: string) => new Date(iso).toLocaleString("en-MY", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

export type AuditRow = AuditEntry & { customer?: string };

/** Read-only, newest first. No edit or delete anywhere, on purpose. */
export function AuditList({ entries, showCustomer }: { entries: AuditRow[]; showCustomer?: boolean }) {
  const list = [...entries].sort((a, b) => b.ts.localeCompare(a.ts) || b.seq - a.seq);
  if (list.length === 0) return <T v="sub">No activity yet.</T>;
  return (
    <Group footer="Entries are added by the system and cannot be edited or deleted.">
      {list.map((e) => (
        <Row
          key={`${e.customer ?? ""}-${e.seq}-${e.hash}`}
          left={<View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: dot(e.actor), alignSelf: "flex-start", marginTop: 6 }} />}
          title={e.summary}
          subtitle={
            <View style={{ gap: 2 }}>
              <T v="foot">{ACTOR[e.actor]}{showCustomer && e.customer ? ` · ${e.customer}` : ""} · {when(e.ts)}</T>
              {e.changes?.map((c) => (
                <T key={c.field} v="foot" style={{ color: C.ink2 }}>{c.field}: {c.from} to {c.to}</T>
              ))}
              <T v="foot">#{e.seq} · {e.hash}</T>
            </View>
          }
        />
      ))}
    </Group>
  );
}
