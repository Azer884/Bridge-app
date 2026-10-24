import { useState } from "react";
import { api, explainError } from "@shared/api";
import { phone } from "@shared/format";
import { COUNTRIES, DEFAULT_COUNTRY, countryByIso, toE164, validNational } from "@shared/countries";
import { useAsync } from "../hooks";
import { useToast } from "../ui/Toast";

export default function Connect() {
  const toast = useToast();
  const [iso, setIso] = useState(DEFAULT_COUNTRY);
  const [national, setNational] = useState("");
  const country = countryByIso(iso);
  const [busy, setBusy] = useState(false);
  const link = useAsync(() => api.whatsappStatus(), [], 3_000);
  const status = link.data?.status ?? "unlinked";

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
    <>
      <div className="page-head">
        <div>
          <h1>WhatsApp</h1>
          <p>Gesir chats with your customers from your own number, on your behalf. It asks you first.</p>
        </div>
      </div>

      <section className="panel">
        <h2>Your number</h2>
        {status === "unlinked" ? (
          <form
            className="form"
            onSubmit={(e) => {
              e.preventDefault();
              run(() => api.linkWhatsapp(toE164(country, national)), "Link request sent");
            }}
          >
            <div className="field">
              <span id="wa-label">WhatsApp number</span>
              <div className="phone-field" role="group" aria-labelledby="wa-label">
                <select className="select" aria-label="Country code" value={iso} onChange={(e) => setIso(e.target.value)}>
                  {COUNTRIES.map((c) => (
                    <option key={c.iso} value={c.iso}>{c.name} (+{c.dial})</option>
                  ))}
                </select>
                <div className="total-input" style={{ borderWidth: "1.5px", borderRadius: 8 }}>
                  <span style={{ fontSize: 16 }}>+{country.dial}</span>
                  <input
                    inputMode="tel"
                    autoComplete="tel-national"
                    placeholder="12 345 6789"
                    style={{ fontSize: 18, fontWeight: 600, width: "100%", fontFamily: "var(--font)" }}
                    value={national}
                    onChange={(e) => setNational(e.target.value)}
                  />
                </div>
              </div>
              <small>The number your customers already message. Leave out the first 0. Sent as +{toE164(country, national) || country.dial}.</small>
            </div>
            <div>
              <button className="btn primary" disabled={busy || !validNational(national)}>
                {busy ? "Linking…" : "Link this number"}
              </button>
            </div>
          </form>
        ) : (
          <div className="form">
            <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
              <b className="num" style={{ fontSize: 26 }}>{phone(link.data?.number ?? undefined)}</b>
              <span className={`status-chip ${status === "linked" ? "approved" : "pending_approval"}`}>
                {status === "linked" ? "Linked" : "Linking, confirm on your phone"}
              </span>
            </div>
            <p>
              {status === "linked"
                ? "Gesir is answering new customer messages on this number."
                : "Gesir is waiting for WhatsApp to confirm the number. This page updates by itself."}
            </p>
            <div>
              <button className="btn danger" disabled={busy} onClick={() => run(() => api.unlinkWhatsapp(), "Number unlinked")}>
                Unlink number
              </button>
            </div>
          </div>
        )}
        {link.error != null && !link.data && <div className="alert" style={{ marginTop: 16 }}>{explainError(link.error)}</div>}
      </section>

      <section className="panel">
        <h2>What Gesir does without asking</h2>
        <div className="notes">
          <div className="note assume">Answers customers and asks the job questions, one at a time.</div>
          <div className="note assume">Drafts a price from what the customer told it.</div>
        </div>
        <h2 style={{ marginTop: 20 }}>What it always asks you first</h2>
        <div className="notes">
          <div className="note flag">Sending any price. The customer gets it only after you approve.</div>
          <div className="note flag">Jobs it cannot price. It flags them for an inspection instead of guessing.</div>
        </div>
      </section>
    </>
  );
}

