import { useState } from "react";
import { Link } from "react-router-dom";
import { api, explainError } from "@shared/api";
import { money, timeAgo } from "@shared/format";
import { useAsync } from "../hooks";
import { canDecide, useActor } from "../actor";
import { IArrowOut, ICalendar, IChevron, IClock, ISearch, IUsers } from "../ui/ObIcons";

type Tab = "all" | "submit" | "review" | "approve" | "rejected";
type Row = { id: string; title: string; sub: string; amount: string; kind: "approve" | "reply" | "rejected"; at?: string };

const greeting = (h: number) => (h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening");

/** Orbyte's dashboard, for a painting business: today's jobs, then everything that needs a person. */
export default function Dashboard() {
  const { me } = useActor();
  const now = new Date();
  const dayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const dayEnd = new Date(dayStart.getTime() + 86_400_000);
  const today = useAsync(() => api.listBookings(dayStart.toISOString(), dayEnd.toISOString()), [], 30_000);
  const quotes = useAsync(
    async () => [...(await api.listQuotes("pending_approval")), ...(await api.listQuotes("needs_inspection"))],
    [me?.id],
    10_000,
  );
  const customers = useAsync(() => api.listCustomers(), [me?.id], 10_000);
  const rejectedQuotes = useAsync(() => api.listQuotes("rejected"), [me?.id], 10_000);
  const [tab, setTab] = useState<Tab>("all");
  const [query, setQuery] = useState("");
  const [closed, setClosed] = useState<Record<string, boolean>>({});
  const [jobsOpen, setJobsOpen] = useState(true);

  const decide = canDecide(me);
  const todo: Row[] = (quotes.data ?? []).map((q) => ({
    id: q.user_id,
    title: `Approve the estimate for ${q.customer}`,
    sub: q.status === "needs_inspection" ? "Needs a site inspection first" : q.job.address ?? q.user_id,
    amount: q.quote ? money(q.quote.approved_total ?? q.quote.total, q.quote.currency) : "",
    kind: "approve",
    at: q.updated_at,
  }));
  const replies: Row[] = (customers.data ?? [])
    .filter((c) => (c.needs_human || c.attention) && !todo.some((t) => t.id === c.user_id))
    .map((c) => ({ id: c.user_id, title: `Reply to ${c.name ?? "a customer"}`, sub: "The customer asked for a person", amount: "", kind: "reply" }));
  const rejectedRows: Row[] = (rejectedQuotes.data ?? []).map((q) => ({
    id: q.user_id,
    title: `Rejected: estimate for ${q.customer}`,
    sub: (q.quote as { rejected?: { reason?: string } } | null)?.rejected?.reason ?? q.job.address ?? q.user_id,
    amount: q.quote ? money(q.quote.total, q.quote.currency) : "",
    kind: "rejected",
    at: q.updated_at,
  }));
  const q = query.trim().toLowerCase();
  const match = (r: Row) => !q || `${r.title} ${r.sub}`.toLowerCase().includes(q);
  const approve = (decide ? todo : []).filter(match);
  const review = (decide ? [] : todo).concat(replies).filter(match);
  const rejected = rejectedRows.filter(match);
  const groups = [
    { key: "approve", title: "Estimates to approve", note: "Waiting for an approver", rows: approve, show: tab === "all" || tab === "approve" },
    { key: "review", title: decide ? "Customers waiting" : "To review", note: decide ? "Need a reply from a person" : "You can read these, an approver decides", rows: review, show: tab === "all" || tab === "review" },
    { key: "rejected", title: "Rejected estimates", note: "The customer was told. Change the values to put one back for approval", rows: rejected, show: tab === "all" || tab === "rejected" },
  ].filter((g) => g.show && g.rows.length);
  const allClosed = groups.length > 0 && groups.every((g) => closed[g.key]);
  const jobs = (today.data ?? []).filter((b) => b.status !== "cancelled").sort((a, b) => a.start.localeCompare(b.start));
  const clock = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const first = (me?.name ?? "").split(" ")[0];
  const tabs: [Tab, string][] = [
    ["all", `All (${approve.length + review.length + rejected.length})`],
    ["submit", "Submit (0)"],
    ["review", `Review (${review.length})`],
    ["approve", `Approve (${approve.length})`],
    ["rejected", `Rejected (${rejected.length})`],
  ];

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Dashboard</h1>
          <p>{now.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</p>
        </div>
      </div>
      <p className="greet"><b>{greeting(now.getHours())}{first ? `, ${first}` : ""}.</b> Here's what needs your attention today.</p>

      <section className="ob-dcard">
        <header>
          <span className="ob-dico"><ICalendar /></span>
          <span className="ob-dhead">
            <b>Jobs today</b>
            <span className="ob-count">{jobs.length} {jobs.length === 1 ? "job" : "jobs"}</span>
            <small>See today's bookings and where the crew is going.</small>
          </span>
          <Link className="btn ob-outline" to="/app/calendar">View job calendar <IArrowOut /></Link>
          <button className="ob-iconbtn" aria-label={jobsOpen ? "Collapse" : "Expand"} aria-expanded={jobsOpen} onClick={() => setJobsOpen(!jobsOpen)}>
            <IChevron open={jobsOpen} />
          </button>
        </header>
        {jobsOpen && (jobs.length === 0 ? (
          <div className="ob-drow calm">
            <span className="ob-dico ok"><IUsers /></span>
            <span><b>No jobs booked today</b><small>The crew has nothing on the calendar today.</small></span>
          </div>
        ) : (
          jobs.map((b) => (
            <Link key={b.id} to={`/app/quotes/${b.user_id}`} className="ob-drow">
              <span className="num ob-time">{clock(b.start)}</span>
              <span><b>{b.customer}</b><small>{b.address || "No address yet"}</small></span>
              <span className={`ob-pill ${b.status === "confirmed" ? "ok" : "warn"}`}>{b.status === "confirmed" ? "Confirmed" : "To confirm"}</span>
            </Link>
          ))
        ))}
      </section>

      {(quotes.error != null || customers.error != null) && <div className="ob-banner bad">{explainError(quotes.error ?? customers.error)}</div>}

      <section className="ob-dcard">
        <header><span className="ob-dhead"><b className="big">Pending Actions</b></span></header>
        <div className="ob-dtools">
          <label className="ob-dsearch"><ISearch /><input placeholder="Search pending items..." value={query} onChange={(e) => setQuery(e.target.value)} /></label>
          <div className="ob-btabs" role="tablist">
            {tabs.map(([k, label]) => (
              <button key={k} role="tab" aria-selected={tab === k} className={`${k}${tab === k ? " on" : ""}`} onClick={() => setTab(k)}>{label}</button>
            ))}
          </div>
          <button className="btn ob-outline" disabled={!groups.length} onClick={() => setClosed(Object.fromEntries(groups.map((g) => [g.key, !allClosed])))}>
            {allClosed ? "Expand all" : "Collapse all"}
          </button>
        </div>
        {!decide && <div className="ob-banner">You are acting as a reviewer. You can open estimates, but only an approver can approve or reject them.</div>}
        {groups.length === 0 && <div className="ob-drow calm center">Nothing is waiting for you.</div>}
        {groups.map((g) => (
          <div key={g.key} className="ob-dgroup">
            <button className="ob-dgroup-head" aria-expanded={!closed[g.key]} onClick={() => setClosed({ ...closed, [g.key]: !closed[g.key] })}>
              <span className="ob-dico sm"><IUsers /></span>
              <b>{g.title}</b>
              <span className="ob-count">{g.rows.length}</span>
              <span className="ob-dnote">{g.note}</span>
              <IChevron open={!closed[g.key]} />
            </button>
            {!closed[g.key] && g.rows.map((r) => (
              <div key={r.id + r.kind} className="ob-drow item">
                <span><b>{r.title}</b><small>{r.sub}</small></span>
                <span className="mute">{r.kind === "approve" ? "Approver" : "Owner"}</span>
                <span className={`ob-status ${r.kind}`}><IClock />{r.kind === "approve" ? "Pending Approval" : r.kind === "rejected" ? "Rejected" : "Needs Reply"}</span>
                <span className="mute num">{r.amount || (r.at ? timeAgo(r.at) : "")}</span>
                <Link className="ob-link" to={`/app/quotes/${r.id}`}>{r.kind === "approve" && decide ? "Go to approval" : "Open"} <IArrowOut /></Link>
              </div>
            ))}
          </div>
        ))}
      </section>
    </>
  );
}
