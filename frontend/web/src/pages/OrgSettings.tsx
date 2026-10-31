import { Link, useSearchParams } from "react-router-dom";
import { api, explainError } from "@shared/api";
import { timeAgo } from "@shared/format";
import { useAsync } from "../hooks";
import { useState } from "react";
import { COUNTRIES, DEFAULT_COUNTRY, countryByIso, toE164, validNational } from "@shared/countries";
import { phone } from "@shared/format";
import { useToast } from "../ui/Toast";
import Personas from "./Personas";
import Status from "./Status";

const TABS = [
  { id: "integrations", label: "Integrations" },
  { id: "personas", label: "Personas" },
  { id: "status", label: "Status" },
] as const;
type TabId = (typeof TABS)[number]["id"];

/** Orbyte's Organization settings. WhatsApp is under Integrations; Personas and Status are tabs. */
export default function OrgSettings() {
  const [params, setParams] = useSearchParams();
  const asked = params.get("tab");
  const tab: TabId = TABS.some((t) => t.id === asked) ? (asked as TabId) : "integrations";

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Organization settings</h1>
          <p>Manage how this business connects to services and how Gesir talks to customers.</p>
        </div>
      </div>
      <div className="ob-utabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? "on" : ""} onClick={() => setParams({ tab: t.id })}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === "integrations" && <Integrations />}
      {tab !== "integrations" && (
        <div className="ob-embed">
          {tab === "personas" && <Personas />}
          {tab === "status" && <Status />}
        </div>
      )}
    </>
  );
}

function Integrations() {
  const events = useAsync(() => api.listEvents(30), [], 10_000);
  return (
    <>
      <section className="panel ob-card">
        <div className="ob-row">
          <span>
            <b>Gesir: quotes and customer chat</b>
            <small>Prepares price estimates from WhatsApp chats and asks an approver before anything is sent.</small>
          </span>
          <span className="ob-pill ok">Built in</span>
          <Link className="ob-link" to="/app/pipeline">Open projects ↗</Link>
        </div>
      </section>
      <WhatsAppRow />
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

/** The WhatsApp number Gesir answers on, with an Unlink button beside it. */
function WhatsAppRow() {
  const toast = useToast();
  const link = useAsync(() => api.whatsappStatus(), [], 5_000);
  const [iso, setIso] = useState(DEFAULT_COUNTRY);
  const [national, setNational] = useState("");
  const [busy, setBusy] = useState(false);
  const status = link.data?.status ?? "unlinked";
  const country = countryByIso(iso);

  async function run(fn: () => Promise<unknown>, ok: string) {
    setBusy(true);
    try {
      await fn();
      toast(ok);
      await link.reload();
    } catch (e) {
      toast(explainError(e), true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ob-list">
      <div className="ob-item">
        <span className="ob-ico">W</span>
        <span className="ob-item-main">
          <b>WhatsApp</b>
          {status !== "unlinked" && <span className={`ob-badge ${status === "linked" ? "ok" : "warn"}`}>{status === "linked" ? "Linked" : "Confirm on your phone"}</span>}
          <small>The number customers message. Gesir answers on it.</small>
        </span>
        {status === "unlinked" ? (
          <form className="ob-item-actions" onSubmit={(e) => { e.preventDefault(); run(() => api.linkWhatsapp(toE164(country, national)), "Link request sent"); }}>
            <select aria-label="Country code" value={iso} onChange={(e) => setIso(e.target.value)}>
              {COUNTRIES.map((c) => <option key={c.iso} value={c.iso}>{c.name} (+{c.dial})</option>)}
            </select>
            <input inputMode="tel" placeholder="12 345 6789" aria-label="WhatsApp number" value={national} onChange={(e) => setNational(e.target.value)} />
            <button className="btn primary" disabled={busy || !validNational(national)}>Link</button>
          </form>
        ) : (
          <span className="ob-item-actions">
            <b className="num">{phone(link.data?.number ?? undefined)}</b>
            <button className="btn danger-o" disabled={busy} onClick={() => run(() => api.unlinkWhatsapp(), "Number unlinked")}>Unlink</button>
          </span>
        )}
      </div>
    </div>
  );
}
