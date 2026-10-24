import type { ChatMessage, Photo } from "@shared/types";
import { phone } from "@shared/format";
import { Lightbox, PhotoGrid } from "./Lightbox";
import { useState } from "react";

const time = (iso: string) => new Date(iso).toLocaleString("en-MY", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
const WHO = { customer: "Customer", assistant: "Gesir", owner: "You" } as const;

export function ChatPanel({ name, number, chat, photos }: { name: string; number: string; chat: ChatMessage[]; photos: Photo[] }) {
  const [open, setOpen] = useState<number | null>(null);
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
      </section>
      <section className="panel">
        <h2>Photos from the customer</h2>
        <PhotoGrid photos={photos} onOpen={setOpen} />
      </section>
      {open != null && <Lightbox photos={photos} index={open} onClose={() => setOpen(null)} />}
    </>
  );
}
