import { useEffect, useState } from "react";
import { api, apiMode, explainError } from "@shared/api";
import { timeAgo } from "@shared/format";
import { useAsync } from "../hooks";

type Pool = { state?: string; idle?: number; busy?: number; queued?: number };

/** The backend sends the worker pools as JSON text; show them as plain rows. */
function pools(detail: string | undefined): { text?: Pool; vision?: Pool } {
  try {
    const j = JSON.parse(detail ?? "");
    return j && typeof j === "object" ? j : {};
  } catch {
    return {};
  }
}

const TONE: Record<string, string> = { ready: "ok", waking: "warn", down: "bad" };
const WORD: Record<string, string> = { ready: "Ready", waking: "Waking up", down: "Not responding" };

export default function Status() {
  const health = useAsync(() => api.modelHealth(), [], 5_000);
  const events = useAsync(() => api.listEvents(50), [], 10_000);
  const [onlyFailed, setOnlyFailed] = useState(false);
  const [waited, setWaited] = useState(0);
  const state = health.data?.state;
  const p = pools(health.data?.detail);

  useEffect(() => {
    if (state !== "waking") return setWaited(0);
    const id = setInterval(() => setWaited((w) => w + 1), 1000);
    return () => clearInterval(id);
  }, [state]);

  const mm = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  const list = (events.data ?? []).filter((e) => !onlyFailed || !e.ok);
  const rows: { name: string; what: string; pool?: Pool }[] = [
    { name: "Chat model", what: "Writes the replies to customers.", pool: p.text },
    { name: "Photo model", what: "Reads the wall and ceiling photos.", pool: p.vision },
  ];

  return (
    <>
      <div className="ob-sec-head">
        <div>
          <h2 className="ob-sec">Status</h2>
          <p className="ob-sec-sub">Is the assistant awake, and what happened recently. Useful when a customer says nothing came back.</p>
        </div>
        <span className="ob-badge">{apiMode() === "mock" ? "Sample data" : "Live backend"}</span>
      </div>

      {health.error != null && !health.data && <div className="ob-banner bad">{explainError(health.error)}</div>}
      {state === "waking" && (
        <div className="ob-banner warn">
          The models are waking up after a quiet spell. This takes 2 to 5 minutes (waiting {mm(waited)}). Customer replies are slow until it finishes.
        </div>
      )}

      <div className="ob-list">
        {rows.map((r) => {
          const s = r.pool?.state ?? state ?? "waking";
          return (
            <div key={r.name} className="ob-item">
              <span className="ob-ico">{r.name.slice(0, 1)}</span>
              <span className="ob-item-main">
                <b>{r.name}</b>
                <span className={`ob-badge ${TONE[s] ?? ""}`}>{WORD[s] ?? s}</span>
                <small>{r.what}</small>
              </span>
              {r.pool && (
                <span className="ob-item-meta">
                  {r.pool.idle ?? 0} idle · {r.pool.busy ?? 0} busy · {r.pool.queued ?? 0} queued
                </span>
              )}
            </div>
          );
        })}
      </div>

      <div className="ob-sec-head" style={{ marginTop: 24 }}>
        <div>
          <h2 className="ob-sec">Recent events</h2>
          <p className="ob-sec-sub">Messages, approvals and errors, newest first.</p>
        </div>
        <label className="ob-check">
          <input type="checkbox" checked={onlyFailed} onChange={(e) => setOnlyFailed(e.target.checked)} />
          Failures only
        </label>
      </div>
      {events.error != null && !events.data && <div className="ob-banner bad">{explainError(events.error)}</div>}
      {list.length === 0 && events.data ? (
        <div className="ob-list"><div className="ob-item empty-row">{onlyFailed ? "No failures." : "No events yet."}</div></div>
      ) : (
        <div className="ob-list">
          {list.map((e, i) => (
            <div key={i} className="ob-item">
              <span className="ob-item-main">
                <b>{e.kind}</b>
                <span className={`ob-badge ${e.ok ? "ok" : "bad"}`}>{e.ok ? "OK" : "Failed"}</span>
                <small>{e.detail}</small>
              </span>
              <span className="ob-item-meta">{timeAgo(e.ts)}</span>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
