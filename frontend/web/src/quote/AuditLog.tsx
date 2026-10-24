import type { AuditActor, AuditEntry } from "@shared/types";

const ACTOR: Record<AuditActor, string> = { customer: "Customer", ai: "Gesir AI", system: "System", owner: "You" };

const when = (iso: string) =>
  new Date(iso).toLocaleString("en-MY", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

export type AuditRow = AuditEntry & { customer?: string };

/** Read-only, newest first. There is no edit or delete anywhere on purpose. */
export function AuditLog({ entries, showCustomer }: { entries: AuditRow[]; showCustomer?: boolean }) {
  const list = [...entries].sort((a, b) => b.ts.localeCompare(a.ts) || b.seq - a.seq);
  if (list.length === 0) return <div className="empty"><b>No activity yet</b></div>;
  return (
    <>
      <ol className="audit" aria-label="Activity log">
        {list.map((e) => (
          <li key={`${e.customer ?? ""}-${e.seq}-${e.hash}`} className={`audit-item ${e.actor}`}>
            <span className="audit-dot" aria-hidden="true" />
            <div className="audit-body">
              <div className="audit-head">
                <span className={`actor ${e.actor}`}>{ACTOR[e.actor]}</span>
                {showCustomer && e.customer ? <b>{e.customer}</b> : null}
                <time dateTime={e.ts}>{when(e.ts)}</time>
              </div>
              <p>{e.summary}</p>
              {e.changes?.length ? (
                <ul className="audit-changes">
                  {e.changes.map((c) => (
                    <li key={c.field}>
                      <span>{c.field}</span>
                      <s>{c.from}</s>
                      <b>{c.to}</b>
                    </li>
                  ))}
                </ul>
              ) : null}
              <small className="num">#{e.seq} · {e.hash}</small>
            </div>
          </li>
        ))}
      </ol>
      <p className="audit-note">Entries are added by the system and cannot be edited or deleted.</p>
    </>
  );
}
