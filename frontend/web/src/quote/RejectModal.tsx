import { useState } from "react";
import { api, explainError } from "@shared/api";
import { Modal } from "../ui/Modal";

const QUICK = ["Price is too high", "Wrong room size", "Missing a surface or item", "Check the photos again"];
const MIN = 5;

/** The owner turns the draft down and tells Gesir what to change. Nothing is sent to the customer. */
export function RejectModal({ userId, name, onClose, onDone }: { userId: string; name: string; onClose: () => void; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const valid = note.trim().length >= MIN;

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      await api.rejectQuote(userId, note.trim());
      onDone();
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Reject this draft?" onClose={() => !busy && onClose()}>
      <p style={{ marginBottom: 12 }}>Tell Gesir what is wrong. It redrafts the quote for {name}. Nothing is sent to the customer.</p>
      <div className="quick" role="group" aria-label="Common reasons">
        {QUICK.map((q) => (
          <button key={q} type="button" className="btn small" onClick={() => setNote((n) => (n.trim() ? `${n.trim()}. ${q}` : q))}>{q}</button>
        ))}
      </div>
      <label className="field" style={{ marginTop: 12 }}>
        <span>What should Gesir change?</span>
        <textarea className="input" rows={4} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} placeholder="For example: the ceiling is 3 m high, not 2.4 m" aria-invalid={note.length > 0 && !valid} />
        <small className={note.length > 0 && !valid ? "err" : "muted"}>{note.length > 0 && !valid ? "Write a few words so Gesir knows what to fix." : "Saved to the activity log with your name."}</small>
      </label>
      {err != null && <div className="alert" role="alert">{explainError(err)}</div>}
      <div className="row-actions" style={{ marginTop: 16 }}>
        <button className="btn" onClick={onClose} disabled={busy}>Cancel</button>
        <button className="btn danger" onClick={submit} disabled={busy || !valid}>{busy ? "Sending…" : err ? "Try again" : "Reject and redraft"}</button>
      </div>
    </Modal>
  );
}
