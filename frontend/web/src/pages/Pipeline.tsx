import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, explainError } from "@shared/api";
import { money, phone, timeAgo } from "@shared/format";
import { STAGES } from "@shared/params";
import type { PipelineRow, Stage } from "@shared/types";
import { useAsync } from "../hooks";
import { AuditLog } from "../quote/AuditLog";

type View = "table" | "board";

export default function Pipeline() {
  const nav = useNavigate();
  const rows = useAsync(() => api.listPipeline(), [], 20_000);
  const activity = useAsync(() => api.listActivity(14), [], 20_000);
  const [stage, setStage] = useState<Stage | "all">("all");
  const [view, setView] = useState<View>("table");

  const all = rows.data ?? [];
  const counts = useMemo(() => Object.fromEntries(STAGES.map((s) => [s.id, all.filter((r) => r.stage === s.id).length])) as Record<Stage, number>, [all]);
  const shown = (stage === "all" ? all : all.filter((r) => r.stage === stage)).slice().sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""));

  const open = (r: PipelineRow) => nav(`/app/quotes/${r.user_id}`);
  const total = (r: PipelineRow) => (r.quote?.total != null ? money(r.quote.total, r.quote.currency) : "No price yet");

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Pipeline</h1>
          <p>Every job from first message to done. Open one to review it, or check the activity log for what changed.</p>
        </div>
        <div className="tabs" role="tablist" aria-label="View">
          {(["table", "board"] as View[]).map((v) => (
            <button key={v} role="tab" className="tab" aria-selected={view === v} onClick={() => setView(v)}>{v === "table" ? "Table" : "Board"}</button>
          ))}
        </div>
      </div>

      <div className="filters" role="group" aria-label="Filter by stage">
        <button className="fchip" aria-pressed={stage === "all"} onClick={() => setStage("all")}>All <small>{all.length}</small></button>
        {STAGES.map((s) => (
          <button key={s.id} className={`fchip s-${s.id}`} aria-pressed={stage === s.id} onClick={() => setStage(s.id)}>
            {s.label} <small>{counts[s.id] ?? 0}</small>
          </button>
        ))}
      </div>

      {rows.error != null && !rows.data && (
        <div className="alert"><span>{explainError(rows.error)}</span><button className="btn small" onClick={rows.reload}>Try again</button></div>
      )}

      <div className="pipe-layout">
        <div className="pipe-main">
          {rows.loading && !rows.data ? <div className="empty">Loading pipeline…</div> : null}
          {rows.data && shown.length === 0 && (
            <div className="panel empty"><b>No jobs in this stage</b><span>Pick another stage to see more.</span></div>
          )}

          {view === "table" && shown.length > 0 && (
            <div className="panel table-panel">
              <div className="table-wrap">
                <table className="pipe-table">
                  <thead>
                    <tr><th>Customer</th><th>Work</th><th>Stage</th><th className="r">Total</th><th className="r">Updated</th></tr>
                  </thead>
                  <tbody>
                    {shown.map((r) => (
                      <tr key={r.user_id} onClick={() => open(r)}>
                        <td>
                          <Link to={`/app/quotes/${r.user_id}`} onClick={(e) => e.stopPropagation()}><b>{r.job.name ?? phone(r.user_id)}</b></Link>
                          <br /><small className="muted num">{phone(r.job.phone ?? r.user_id)}</small>
                        </td>
                        <td>{r.job.surfaces ?? "Not given"}</td>
                        <td><span className={`stage-chip s-${r.stage}`}>{STAGES.find((s) => s.id === r.stage)?.label}</span></td>
                        <td className="r num">{total(r)}</td>
                        <td className="r muted">{timeAgo(r.updated_at) || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
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
        </div>

        <aside className="panel pipe-activity" aria-label="Recent activity">
          <h2>Recent activity</h2>
          {activity.error != null && !activity.data && <div className="alert">{explainError(activity.error)}</div>}
          {activity.data && <AuditLog entries={activity.data} showCustomer />}
        </aside>
      </div>
    </>
  );
}
