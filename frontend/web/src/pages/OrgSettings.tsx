import { Link } from "react-router-dom";
import { api, explainError } from "@shared/api";
import { timeAgo } from "@shared/format";
import { useAsync } from "../hooks";

export default function OrgSettings() {
  const events = useAsync(() => api.listEvents(30), [], 10_000);
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Organization settings</h1>
          <p>How this business connects to services.</p>
        </div>
      </div>
      <section className="panel ob-card">
        <div className="ob-tabs">
          <span className="ob-tab">Authentication methods</span>
          <span className="ob-tab">Member invitations</span>
          <span className="ob-tab on">Integrations</span>
        </div>
        <div className="ob-row">
          <span>
            <b>Gesir: quotes and customer chat</b>
            <small>Prepares price estimates from WhatsApp chats and asks an approver before anything is sent.</small>
          </span>
          <span className="ob-pill ok">Built in</span>
          <Link className="ob-link" to="/app/quotes">Open quotes ↗</Link>
        </div>
        <div className="ob-row">
          <span>
            <b>WhatsApp</b>
            <small>The number customers message.</small>
          </span>
          <span className="ob-pill mute">Connected</span>
          <Link className="ob-link" to="/app/connect">Manage ↗</Link>
        </div>
      </section>
      <section className="panel ob-card">
        <h2>Recent activity</h2>
        {events.error != null && <div className="alert">{explainError(events.error)}</div>}
        {events.data && events.data.length === 0 && (
          <div className="empty">
            <b>Nothing yet</b>Messages, approvals and errors show here.
          </div>
        )}
        {(events.data ?? []).slice(0, 15).map((e, i) => (
          <div key={i} className="ob-row">
            <span>
              <b>{e.kind}</b>
              <small>{e.detail}</small>
            </span>
            <span className={`ob-pill ${e.ok ? "ok" : "bad"}`}>{e.ok ? "OK" : "Failed"}</span>
            <span className="mute">{timeAgo(e.ts)}</span>
          </div>
        ))}
      </section>
    </>
  );
}
