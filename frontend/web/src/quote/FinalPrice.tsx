import { useState } from "react";
import { api, explainError } from "@shared/api";
import { money, phone } from "@shared/format";
import type { QuoteDraft } from "@shared/types";
import { Modal } from "../ui/Modal";
import { useToast } from "../ui/Toast";

interface Props {
  userId: string;
  name: string;
  number: string;
  quote: QuoteDraft;
  /** The estimate is approved and no final price has been sent yet. */
  open: boolean;
  onSent: () => void;
}

/** After the site visit the owner measures and sends the final price. The backend only accepts it once the estimate was approved. */
export function FinalPrice({ userId, name, number, quote, open, onSent }: Props) {
  const toast = useToast();
  const [raw, setRaw] = useState(String(quote.approved_total ?? quote.total ?? ""));
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);

  const total = Number(raw);
  const valid = raw !== "" && Number.isFinite(total) && total > 0;
  const sent = quote.approved_total ?? quote.total ?? 0;

  if (!open) {
    return quote.final_total != null ? (
      <section className="panel">
        <h2>Final price sent</h2>
        <p className="muted">Estimate {money(quote.approved_total ?? sent, quote.currency)}, final {money(quote.final_total, quote.currency)}.</p>
      </section>
    ) : null;
  }

  async function send() {
    setBusy(true);
    setErr(null);
    try {
      await api.confirmFinal(userId, total);
      setConfirm(false);
      toast(`Final price sent to ${name}`);
      onSent();
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <h2>Final price after the visit</h2>
      <p className="muted" style={{ marginBottom: 14 }}>Estimate sent: {money(sent, quote.currency)}. Measure on site, then send the customer the final price.</p>
      <label className="field">
        <span>Final total</span>
        <div className="total-input" style={{ maxWidth: 260 }}>
          <span>{quote.currency}</span>
          <input inputMode="decimal" value={raw} onChange={(e) => setRaw(e.target.value.replace(/[^0-9.]/g, ""))} aria-invalid={!valid} />
        </div>
        <small className={valid ? "muted" : "err"}>{valid ? "This replaces the estimate for the customer." : "Enter an amount above zero."}</small>
      </label>
      <div className="row-actions" style={{ marginTop: 14 }}>
        <button className="btn primary" disabled={!valid} onClick={() => { setErr(null); setConfirm(true); }}>Send final price</button>
      </div>

      {confirm && (
        <Modal title="Send the final price?" onClose={() => !busy && setConfirm(false)}>
          <ul className="checks">
            <li><b className="num">{money(total, quote.currency)}</b> goes to <b>{phone(number)}</b> on WhatsApp right away. You cannot take the message back.</li>
            <li>It is saved to the activity log.</li>
          </ul>
          {err != null && <div className="alert" role="alert">{explainError(err)}</div>}
          <div className="row-actions" style={{ marginTop: 16 }}>
            <button className="btn" onClick={() => setConfirm(false)} disabled={busy}>Cancel</button>
            <button className="btn primary" onClick={send} disabled={busy}>{busy ? "Sending…" : err ? "Try again" : "Send final price"}</button>
          </div>
        </Modal>
      )}
    </section>
  );
}
