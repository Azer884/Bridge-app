import { useState } from "react";
import { Link } from "react-router-dom";
import { api, explainError } from "@shared/api";
import { money, timeAgo } from "@shared/format";
import { useAsync } from "../hooks";
import { canDecide, useActor } from "../actor";

type Tab = "all" | "submit" | "review" | "approve";
type Row = { id: string; title: string; sub: string; amount: string; kind: "approve" | "reply"; at?: string };

/** What needs a person: estimates to approve or inspect, and customers who asked for someone. */
export default function Dashboard() {
  const { me } = useActor();
  const quotes = useAsync(
    async () => [...(await api.listQuotes("pending_approval")), ...(await api.listQuotes("needs_inspection"))],
    [me?.id],
    10_000,
  );
  const customers = useAsync(() => api.listCustomers(), [me?.id], 10_000);
  const [tab, setTab] = useState<Tab>("all");

  const decide = canDecide(me);
  const todo: Row[] = (quotes.data ?? []).map((q) => ({
    id: q.user_id,
    title: `Estimate for ${q.customer}`,
    sub: q.status === "needs_inspection" ? "Needs a site inspection" : "Pending approval",
    amount: q.quote ? money(q.quote.approved_total ?? q.quote.total, q.quote.currency) : "",
    kind: "approve" as const,
    at: q.updated_at,
  }));
  const replies: Row[] = (customers.data ?? [])
    .filter((c) => (c.needs_human || c.attention) && !todo.some((t) => t.id === c.user_id))
    .map((c) => ({
      id: c.user_id,
      title: `Reply to ${c.name ?? "customer"}`,
      sub: "The customer needs a person",
      amount: "",
      kind: "reply" as const,
      at: undefined,
    }));
  const approve = decide ? todo : [];
  const review = (decide ? [] : todo).concat(replies);
  const rows = tab === "approve" ? approve : tab === "review" ? review : tab === "submit" ? [] : [...approve, ...review];
  const first = (me?.name ?? "").split(" ")[0];
  const tabs: [Tab, string][] = [
    ["all", `All (${approve.length + review.length})`],
    ["submit", "Submit (0)"],
    ["review", `Review (${review.length})`],
    ["approve", `Approve (${approve.length})`],
  ];

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Dashboard</h1>
          <p>{new Date().toLocaleDateString([], { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</p>
        </div>
      </div>
      <p className="greet">
        <b>Good day{first ? `, ${first}` : ""}.</b> Here is what needs your attention today.
      </p>

      {(quotes.error != null || customers.error != null) && <div className="alert">{explainError(quotes.error ?? customers.error)}</div>}
      <section className="panel ob-card">
        <h2>Pending Actions</h2>
        <div className="ob-tabs" role="tablist">
          {tabs.map(([k, label]) => (
            <button key={k} role="tab" aria-selected={tab === k} className={`ob-tab ${k}${tab === k ? " on" : ""}`} onClick={() => setTab(k)}>
              {label}
            </button>
          ))}
        </div>
        {!decide && <p className="note">Your role ({me?.module_role}) can review but not approve or reject.</p>}
        {rows.length === 0 ? (
          <div className="empty">
            <b>No pending items</b>Nothing is waiting for you.
          </div>
        ) : (
          rows.map((r) => (
            <div key={r.id + r.kind} className="ob-row">
              <span>
                <b>{r.title}</b>
                <small>
                  {r.sub}
                  {r.at ? ` · ${timeAgo(r.at)}` : ""}
                </small>
              </span>
              <span className={`ob-pill ${r.kind === "approve" ? "warn" : "mute"}`}>{r.kind === "approve" ? "Needs approval" : "Needs you"}</span>
              <span className="num">{r.amount}</span>
              <Link className="ob-link" to={`/app/quotes/${r.id}`}>
                {r.kind === "approve" && decide ? "Go to approval" : "Open"} ↗
              </Link>
            </div>
          ))
        )}
      </section>
    </>
  );
}
