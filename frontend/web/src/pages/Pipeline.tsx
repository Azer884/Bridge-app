import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, explainError } from "@shared/api";
import { jobSummary, jobTitle, money, phone, timeAgo } from "@shared/format";
import { STAGES } from "@shared/params";
import type { PipelineRow, Stage } from "@shared/types";
import { useAsync } from "../hooks";
import { AuditLog } from "../quote/AuditLog";

type View = "table" | "board";

/** Orbyte's Project List: every job (Orbyte calls it a project) with search, status and source filters. */
export default function Pipeline() {
  const nav = useNavigate();
  const rows = useAsync(() => api.listPipeline(), [], 20_000);
  const activity = useAsync(() => api.listActivity(14), [], 20_000);
  const [stage, setStage] = useState<Stage | "all">("all");
  const [view, setView] = useState<View>("table");
  const [query, setQuery] = useState("");

  const all = rows.data ?? [];
  const q = query.trim().toLowerCase();
  const shown = useMemo(
    () =>
      all
        .filter((r) => (stage === "all" || r.stage === stage) && (!q || `${r.job.name ?? ""} ${r.user_id} ${r.job.surfaces ?? ""}`.toLowerCase().includes(q)))
        .sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? "")),
    [all, stage, q],
  );

  const open = (r: PipelineRow) => nav(`/app/quotes/${r.user_id}`);
  const total = (r: PipelineRow) => (r.quote?.total != null ? money(r.quote.total, r.quote.currency) : "-");
  const label = (s: Stage) => STAGES.find((x) => x.id === s)?.label ?? s;
  const tone = (s: Stage) => (s === "completed" || s === "scheduled" || s === "quote_sent" ? "ok" : s === "rejected" ? "bad" : s === "requires_approval" ? "warn" : "mute");

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Project List</h1>
          <p>Manage project records and tasks. Open one to review it, approve it, chat with the customer or check what changed.</p>
        </div>
        <button className="btn" onClick={() => { rows.reload(); activity.reload(); }}>↻ Sync all</button>
      </div>

      <section className="panel ob-card ob-filters">
        <label className="grow">Search<input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search projects" /></label>
        <label>Status
          <select value={stage} onChange={(e) => setStage(e.target.value as Stage | "all")}>
            <option value="all">All statuses</option>
            {STAGES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </label>
        <label>Source<select defaultValue="gesir"><option value="all">All sources</option><option value="gesir">Gesir</option></select></label>
        <div className="ob-tabs" role="tablist" aria-label="View">
          {(["table", "board"] as View[]).map((v) => (
            <button key={v} role="tab" aria-selected={view === v} className={`ob-tab${view === v ? " on" : ""}`} onClick={() => setView(v)}>{v === "table" ? "Table" : "Board"}</button>
          ))}
        </div>
      </section>

      {rows.error != null && !rows.data && (
        <div className="alert"><span>{explainError(rows.error)}</span><button className="btn small" onClick={rows.reload}>Try again</button></div>
      )}
      {rows.loading && !rows.data ? <div className="empty">Loading projects…</div> : null}
      {rows.data && shown.length === 0 && <div className="panel ob-card empty"><b>No projects</b><span>Nothing matches these filters.</span></div>}

      {view === "table" && shown.length > 0 && (
        <section className="panel ob-card">
          <table className="ob-table clickable">
            <thead>
              <tr><th>Project</th><th>Client</th><th>Status</th><th>Source</th><th>Amount</th><th>Updated</th><th></th></tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.user_id} onClick={() => open(r)}>
                  <td><b>{jobTitle(r.job)} for {r.job.name ?? phone(r.user_id)}</b><br /><small className="muted">{jobSummary(r.job)}</small></td>
                  <td>{r.job.name ?? phone(r.user_id)}<br /><small className="muted num">{phone(r.job.phone ?? r.user_id)}</small></td>
                  <td><span className={`ob-pill ${tone(r.stage)}`}>{label(r.stage)}</span></td>
                  <td>Gesir</td>
                  <td className="num">{total(r)}</td>
                  <td className="muted">{timeAgo(r.updated_at) || "-"}</td>
                  <td><Link className="ob-link" to={`/app/quotes/${r.user_id}`} onClick={(e) => e.stopPropagation()}>Open</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {view === "board" && rows.data && (
        <div className="board">
          {STAGES.filter((s) => stage === "all" || s.id === stage).map((s) => {
            const col = shown.filter((r) => r.stage === s.id);
            return (
              <section key={s.id} className={`col s-${s.id}`} aria-label={s.label}>
                <h3>{s.label} <small>{col.length}</small></h3>
                {col.length === 0 && <p className="muted">None</p>}
                {col.map((r) => (
                  <Link key={r.user_id} to={`/app/quotes/${r.user_id}`} className="kcard">
                    <b>{r.job.name ?? phone(r.user_id)}</b>
                    <span>{r.job.surfaces ?? "Not given"}</span>
                    <span className="num">{total(r)}</span>
                    <small className="muted">{timeAgo(r.updated_at)}</small>
                  </Link>
                ))}
              </section>
            );
          })}
        </div>
      )}

      <section className="panel ob-card" aria-label="Recent activity">
        <h2>Recent activity</h2>
        {activity.error != null && !activity.data && <div className="alert">{explainError(activity.error)}</div>}
        {activity.data && <AuditLog entries={activity.data} showCustomer />}
      </section>
    </>
  );
}
