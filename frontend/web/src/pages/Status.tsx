import { useEffect, useState } from "react";
import { api, apiMode, explainError } from "@shared/api";
import { timeAgo } from "@shared/format";
import { useAsync } from "../hooks";

export default function Status() {
  const health = useAsync(() => api.modelHealth(), [], 5_000);
  const events = useAsync(() => api.listEvents(50), [], 10_000);
  const [onlyFailed, setOnlyFailed] = useState(false);
  const [waited, setWaited] = useState(0);
  const state = health.data?.state;

  useEffect(() => {
    if (state !== "waking") return setWaited(0);
    const id = setInterval(() => setWaited((w) => w + 1), 1000);
    return () => clearInterval(id);
  }, [state]);

  const mm = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  const list = (events.data ?? []).filter((e) => !onlyFailed || !e.ok);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Status</h1>
          <p>Is the assistant awake, and what happened recently. Useful when a customer says nothing came back.</p>
        </div>
        <span className="pill" style={{ background: "var(--chip)", color: "var(--ink)" }}>
          {apiMode() === "mock" ? "Sample data" : "Live backend"}
        </span>
      </div>

      <section className="panel health" aria-live="polite">
        <div className={`orb ${state ?? ""}`} />
        <div>
          <h2>
            {state === "waking" ? "Models are waking up" : state === "ready" ? "Models are ready" : state === "down" ? "Models are not responding" : "Checking models"}
          </h2>
          <p>
            {health.error != null && !health.data
              ? explainError(health.error)
              : state === "waking"
                ? `This is normal after a quiet spell and takes 2 to 5 minutes. Waiting ${mm(waited)}. Customer replies will be slow until it finishes.`
                : health.data?.detail}
          </p>
          {state === "waking" && <div className="progress"><i /></div>}
        </div>
      </section>

      <section className="panel">
        <div className="page-head" style={{ marginBottom: 8 }}>
          <h2 style={{ margin: 0 }}>Recent events</h2>
          <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input type="checkbox" checked={onlyFailed} onChange={(e) => setOnlyFailed(e.target.checked)} />
            Failures only
          </label>
        </div>
        {events.error != null && !events.data && <div className="alert">{explainError(events.error)}</div>}
        {list.length === 0 && events.data ? (
          <div className="empty"><b>{onlyFailed ? "No failures" : "No events yet"}</b></div>
        ) : (
          <div className="events">
            {list.map((e, i) => (
              <div key={i} className={`event${e.ok ? "" : " bad"}`}>
                <span className="tick" />
                <div><b>{e.kind}</b><small>{timeAgo(e.ts)}</small></div>
                <div>{e.detail}</div>
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  );
}


