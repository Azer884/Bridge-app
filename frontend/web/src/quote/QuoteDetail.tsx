import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, explainError } from "@shared/api";
import { money, phone } from "@shared/format";
import { STAGES, validateParams } from "@shared/params";
import type { ParamValue, QuoteDetail as Detail, QuoteDraft } from "@shared/types";
import { useAsync } from "../hooks";
import { Modal } from "../ui/Modal";
import { useToast } from "../ui/Toast";
import { AuditLog } from "./AuditLog";
import { FinalPrice } from "./FinalPrice";
import { ChatPanel } from "./ChatPanel";
import { ParamsForm } from "./ParamsForm";
import { PdfPanel } from "./PdfPanel";
import { PricePreview, type CalcState } from "./PricePreview";

type Tab = "quote" | "chat" | "activity";

export function QuoteDetail({ userId, onChanged }: { userId: string; onChanged: () => void }) {
  const nav = useNavigate();
  const { data, error, loading, reload } = useAsync(() => api.getQuoteDetail(userId), [userId]);

  if (!data) {
    return (
      <>
        <button className="btn small back" onClick={() => nav("/app/quotes")}>Back to list</button>
        {error != null ? (
          <div className="alert">{explainError(error)}<button className="btn small" onClick={reload}>Try again</button></div>
        ) : (
          <div className="panel empty">{loading ? "Loading quote…" : ""}</div>
        )}
      </>
    );
  }
  return <Loaded key={userId + data.status + data.audit.length} d={data} reload={reload} onChanged={onChanged} />;
}

function Loaded({ d, reload, onChanged }: { d: Detail; reload: () => Promise<void>; onChanged: () => void }) {
  const nav = useNavigate();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("quote");

  const params = d.params;
  const server = params?.current ?? {};
  const [values, setValues] = useState<Record<string, ParamValue>>(server);
  const [quote, setQuote] = useState<QuoteDraft | null>(d.quote);
  const [duration, setDuration] = useState<number | null>(d.duration_hours);
  const [calc, setCalc] = useState<CalcState>({ status: "idle" });
  const [manual, setManual] = useState<string | null>(null);
  const [previewed, setPreviewed] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendErr, setSendErr] = useState<unknown>(null);
  const seq = useRef(0);

  const readOnly = d.locked || d.status === "collecting" || !d.quote || !params;
  const errors = useMemo(() => (params ? validateParams(params.schema, values) : {}), [params, values]);
  const hasErrors = Object.keys(errors).length > 0;
  const dirty = JSON.stringify(values) !== JSON.stringify(server);
  const overrides = params ? params.schema.filter((f) => values[f.key] != null && values[f.key] !== params.ai[f.key]).length : 0;

  // Live recalculation: wait for typing to pause, drop answers that arrive late.
  useEffect(() => {
    if (readOnly || !params) return;
    if (!dirty) {
      setQuote(d.quote);
      setDuration(d.duration_hours);
      setCalc({ status: "idle" });
      return;
    }
    if (hasErrors) return;
    const mine = ++seq.current;
    setCalc({ status: "loading" });
    const t = setTimeout(async () => {
      try {
        const r = await api.recalculate(d.user_id, values);
        if (mine !== seq.current) return;
        setQuote(r.quote);
        setDuration(r.duration_hours);
        setCalc({ status: "idle" });
      } catch (e) {
        if (mine !== seq.current) return;
        setCalc({ status: "error", message: `Could not recalculate. ${explainError(e)} The price shown may be out of date.` });
      }
    }, 400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [values]);

  const cur = quote?.currency ?? "MYR";
  const calcTotal = quote?.total ?? 0;
  const manualNum = manual == null ? null : Number(manual);
  const manualValid = manualNum == null || (Number.isFinite(manualNum) && manualNum > 0);
  const manualActive = manualNum != null && manualValid && Math.abs(manualNum - calcTotal) > 0.004;
  const finalTotal = manualActive ? manualNum! : calcTotal;
  const version = JSON.stringify([values, manualActive ? manualNum : null]);
  const pdfStale = previewed !== version;
  const canSend = !readOnly && !hasErrors && calc.status === "idle" && manualValid && finalTotal > 0;

  const stage = STAGES.find((s) => s.id === d.stage);

  async function send() {
    setSending(true);
    setSendErr(null);
    try {
      if (dirty) await api.saveParams(d.user_id, values);
      await api.approveQuote(d.user_id, manualActive ? manualNum! : undefined);
      setConfirm(false);
      toast(`Quote sent to ${d.job.name ?? "customer"}`);
      onChanged();
      await reload();
    } catch (e) {
      setSendErr(e);
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      <button className="btn small back" onClick={() => nav("/app/quotes")}>Back to list</button>

      <section className="panel">
        <div className="detail-head">
          <div>
            <h2>{d.job.name ?? "Unnamed customer"}</h2>
            <p className="num">{phone(d.job.phone ?? d.user_id)}</p>
            <p className="muted">
              {d.job.address ?? "No address yet"}
              {d.job.location && <> · <a href={d.job.location.maps_url} target="_blank" rel="noreferrer">Open in Maps</a></>}
            </p>
            {(d.needs_human || d.attention) && <p className="alert warm" role="status">Needs you: open the chat tab to reply.</p>}
          </div>
          <span className={`stage-chip s-${d.stage}`} title={stage?.hint}>{stage?.label}</span>
        </div>
        {d.job.preferred_datetime && <p className="hint" style={{ marginTop: 14 }}>Customer asked for: <b>{d.job.preferred_datetime}</b></p>}
        <div className="tabs" role="tablist" aria-label="Quote sections" style={{ marginTop: 16 }}>
          {([["quote", "Quote"], ["chat", `Chat and photos (${d.photos.length})`], ["activity", `Activity (${d.audit.length})`]] as [Tab, string][]).map(([id, label]) => (
            <button key={id} role="tab" className="tab" aria-selected={tab === id} onClick={() => setTab(id)}>{label}</button>
          ))}
        </div>
      </section>

      {tab === "chat" && <ChatPanel name={d.job.name ?? "Customer"} number={d.job.phone ?? d.user_id} chat={d.chat} photos={d.photos} userId={d.user_id} needsHuman={d.needs_human} humanActive={d.human_active} onSent={() => void reload()} />}

      {tab === "activity" && (
        <section className="panel">
          <h2>Activity</h2>
          <AuditLog entries={d.audit} />
        </section>
      )}

      {tab === "quote" && (
        <>
          {d.status === "needs_inspection" && (
            <section className="panel">
              <h2>Send someone to inspect</h2>
              <p style={{ marginBottom: 16 }}>Gesir could not price this job from chat alone. Look at the photos, visit the site, then reply to the customer yourself.</p>
              <div className="row-actions">
                <button className="btn" onClick={() => setTab("chat")}>See photos and chat</button>
                <Link className="btn primary" to={`/app/calendar?book=${d.user_id}`}>Book a site visit</Link>
              </div>
            </section>
          )}

          {d.status === "collecting" && (
            <div className="alert info">Gesir is still asking the customer questions. Fields fill in as they answer, and the price appears when everything is known.</div>
          )}

          {quote && (quote.flags.length > 0 || quote.assumptions.length > 0) && (
            <section className="panel">
              <h2>Check before sending</h2>
              <div className="notes">
                {quote.flags.map((f) => <div key={f} className="note flag">{f}</div>)}
                {quote.assumptions.map((a) => <div key={a} className="note assume">Assumed: {a}</div>)}
              </div>
            </section>
          )}

          {params && (
            <section className="panel">
              <div className="panel-title">
                <h2>What Gesir read</h2>
                {overrides > 0 && !readOnly && (
                  <span className="status-chip pending_approval">{overrides} changed by you</span>
                )}
              </div>
              {!readOnly && <p className="muted" style={{ marginBottom: 14 }}>Fix anything that looks wrong. The price updates as you type.</p>}
              <ParamsForm
                params={params}
                values={values}
                errors={errors}
                readOnly={readOnly}
                onChange={(k, v) => setValues((s) => ({ ...s, [k]: v }))}
                onReset={(k) => setValues((s) => ({ ...s, [k]: params.ai[k] }))}
              />
            </section>
          )}

          {quote && (
            <section className="panel">
              <h2>{d.locked ? "Price sent" : "Price"}</h2>
              <PricePreview quote={quote} before={d.quote!} calc={calc} durationHours={duration} />
              {!readOnly && (
                <div className="manual">
                  <label className="field">
                    <span>Adjust the final total (optional)</span>
                    <div className="total-input" style={{ maxWidth: 260 }}>
                      <span>{cur}</span>
                      <input
                        inputMode="decimal"
                        value={manual ?? String(calcTotal)}
                        onChange={(e) => setManual(e.target.value.replace(/[^0-9.]/g, ""))}
                        aria-invalid={!manualValid}
                      />
                    </div>
                    <small className={manualValid ? "muted" : "err"}>
                      {!manualValid ? "Enter an amount above zero." : manualActive ? `Replaces the calculated ${money(calcTotal, cur)}.` : "Same as calculated."}
                    </small>
                  </label>
                  {manual != null && <button type="button" className="link" onClick={() => setManual(null)}>Use calculated total</button>}
                </div>
              )}
              {d.locked && <div className="row-actions" style={{ marginTop: 14 }}><Link className="btn primary" to={`/app/calendar?book=${d.user_id}`}>Find a time</Link></div>}
              {!d.locked && !readOnly && duration != null && (
                <div className="row-actions" style={{ marginTop: 14 }}>
                  <Link className="btn small" to={`/app/calendar?book=${d.user_id}`}>See suggested times</Link>
                </div>
              )}
            </section>
          )}

          {quote && (d.status === "approved" || d.status === "completed") && (
            <FinalPrice userId={d.user_id} name={d.job.name ?? "customer"} number={d.job.phone ?? d.user_id} quote={quote} open={d.status === "approved"} onSent={() => { onChanged(); void reload(); }} />
          )}

          {quote && params && (
            <section className="panel">
              <h2>Quote PDF</h2>
              <PdfPanel userId={d.user_id} params={values} version={version} blocked={hasErrors || readOnly && !d.locked} onPreviewed={setPreviewed} />
            </section>
          )}

          {!readOnly && quote && (
            <div className="sendbar">
              <div>
                <small className="muted">The customer gets</small>
                <b className="num">{money(finalTotal, cur)}</b>
              </div>
              <button className="btn primary" disabled={!canSend} onClick={() => { setSendErr(null); setConfirm(true); }}>
                {calc.status === "loading" ? "Recalculating…" : "Approve and send"}
              </button>
            </div>
          )}
          {!readOnly && hasErrors && <p className="err" role="alert">Fix the highlighted values before sending.</p>}
        </>
      )}

      {confirm && (
        <Modal title="Send this quote?" onClose={() => !sending && setConfirm(false)}>
          <ul className="checks">
            <li><b className="num">{money(finalTotal, cur)}</b> goes to <b>{phone(d.job.phone ?? d.user_id)}</b> on WhatsApp from your number, sent by Gesir on your behalf.</li>
            <li>{overrides > 0 || manualActive ? `You changed ${overrides} value${overrides === 1 ? "" : "s"}${manualActive ? " and the total" : ""}. These are saved to the activity log.` : "No changes to what Gesir read."}</li>
            <li className={pdfStale ? "warnline" : ""}>{pdfStale ? "You have not previewed the PDF with these values." : "PDF preview matches these values."}</li>
          </ul>
          <p>You cannot take the message back.</p>
          {sendErr != null && <div className="alert">{explainError(sendErr)}</div>}
          <div className="modal-actions">
            <button className="btn" onClick={() => setConfirm(false)} disabled={sending}>Cancel</button>
            <button className="btn primary" onClick={send} disabled={sending}>{sending ? "Sending…" : sendErr ? "Try again" : "Send quote"}</button>
          </div>
        </Modal>
      )}
    </>
  );
}
