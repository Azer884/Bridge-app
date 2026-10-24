import type { ChatMessage, Photo } from "@shared/types";
import { phone } from "@shared/format";
import { Lightbox, PhotoGrid } from "./Lightbox";
import { useState } from "react";
import { api, explainError } from "@shared/api";
import { useToast } from "../ui/Toast";

const time = (iso: string) => new Date(iso).toLocaleString("en-MY", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
const WHO = { customer: "Customer", assistant: "Gesir", owner: "You" } as const;

interface ChatProps {
  name: string;
  number: string;
  chat: ChatMessage[];
  photos: Photo[];
  userId: string;
  needsHuman?: boolean;
  humanActive?: boolean;
  onSent: () => void;
}

export function ChatPanel({ name, number, chat, photos, userId, needsHuman, humanActive, onSent }: ChatProps) {
  const toast = useToast();
  const [open, setOpen] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function send() {
    if (!text.trim() || busy) return;
    setBusy(true);
    setErr(null);
    try {
      await api.sendOwnerMessage(userId, text.trim());
      setText("");
      toast(`Message sent to ${name}`);
      onSent();
    } catch (e) {
      setErr(explainError(e));
    } finally {
      setBusy(false);
    }
  }

  async function resume() {
    try {
      await api.resumeAssistant(userId);
      toast("The assistant is replying again");
      onSent();
    } catch (e) {
      setErr(explainError(e));
    }
  }
  const byId = new Map(photos.map((p, i) => [p.id, i]));

  return (
    <>
      <section className="panel">
        <div className="chat-head">
          <div>
            <h2 style={{ margin: 0 }}>{name}</h2>
            <p className="num muted">{phone(number)}</p>
          </div>
          <a className="btn small" href={`https://wa.me/${number.replace(/\D/g, "")}`} target="_blank" rel="noreferrer">Open in WhatsApp</a>
        </div>
        <div className="chat" role="log" aria-label="WhatsApp conversation">
          {chat.length === 0 ? <p className="muted">No messages yet.</p> : null}
          {chat.map((m) => (
            <div key={m.id} className={`bubble-row ${m.role}`}>
              <div className="chat-bubble">
                <small>{WHO[m.role]}</small>
                <p>{m.text}</p>
                {m.photo_ids?.length ? (
                  <div className="chat-photos">
                    {m.photo_ids.map((id) => {
                      const i = byId.get(id);
                      const p = i != null ? photos[i] : null;
                      return p ? (
                        <button key={id} onClick={() => setOpen(i!)} aria-label={`Open photo: ${p.caption}`}>
                          <img src={p.url} alt={p.caption} loading="lazy" />
                        </button>
                      ) : null;
                    })}
                  </div>
                ) : null}
                <time dateTime={m.ts}>{time(m.ts)}</time>
              </div>
            </div>
          ))}
        </div>
        {needsHuman && !humanActive && <p className="alert warm" role="status">The assistant asked for a person. Write to {name} below.</p>}
        {humanActive && (
          <p className="hint" role="status">
            You are replying by hand, so the assistant is paused for {name}. <button className="btn small" onClick={resume}>Let the assistant continue</button>
          </p>
        )}
        <div className="composer">
          <textarea
            className="input"
            rows={2}
            maxLength={1000}
            placeholder={`Write to ${name} on WhatsApp, in place of the assistant`}
            value={text}
            onChange={(e) => setText(e.target.value)}
            aria-label={`Message to ${name}`}
          />
          <button className="btn" onClick={send} disabled={busy || !text.trim()}>{busy ? "Sending…" : "Send"}</button>
        </div>
        {err && <div className="alert" role="alert">{err}</div>}
      </section>
      <section className="panel">
        <h2>Photos from the customer</h2>
        <PhotoGrid photos={photos} onOpen={setOpen} />
      </section>
      {open != null && <Lightbox photos={photos} index={open} onClose={() => setOpen(null)} />}
    </>
  );
}
