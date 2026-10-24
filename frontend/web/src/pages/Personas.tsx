import { useEffect, useState } from "react";
import { api, explainError } from "@shared/api";
import { PERSONA_LIMITS, type Persona } from "@shared/types";
import { useAsync } from "../hooks";
import { useToast } from "../ui/Toast";

const COLORS = ["#083c57", "#129a8d", "#1c8f63", "#041b2d", "#3fb5c8", "#59a36f"];
const FIELDS: { key: keyof Persona; label: string; hint: string; area: boolean }[] = [
  { key: "name", label: "Name", hint: "What customers see as the sender.", area: false },
  { key: "style", label: "Voice", hint: "How the assistant talks. Tone, length, slang.", area: true },
  { key: "greeting", label: "Greeting", hint: "First message. Use {name}, {business} and {owner}.", area: true },
  { key: "service_question", label: "First question", hint: "Asked after the greeting.", area: true },
  { key: "closing", label: "Closing", hint: "Sent when the chat is done and the quote is drafted.", area: true },
];
const BLANK: Persona = { name: "", style: "", greeting: "", service_question: "", closing: "" };

const fill = (t: string, p: Persona) =>
  t.replaceAll("{name}", p.name || "Name").replaceAll("{business}", "Your Business").replaceAll("{owner}", "the owner");

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");

export default function Personas() {
  const toast = useToast();
  const { data, error, loading, reload } = useAsync(() => api.listPersonas(), []);
  const [sel, setSel] = useState<string | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [form, setForm] = useState<Persona>(BLANK);
  const [busy, setBusy] = useState(false);

  const personas = data?.personas ?? {};
  const active = data?.active;

  useEffect(() => {
    if (data && !isNew) {
      const id = sel && data.personas[sel] ? sel : data.active;
      setSel(id);
      setForm(data.personas[id] ?? BLANK);
    }
  }, [data]); // eslint-disable-line react-hooks/exhaustive-deps

  const over = FIELDS.some((f) => form[f.key].length > PERSONA_LIMITS[f.key]);
  const empty = FIELDS.some((f) => !form[f.key].trim());

  function pick(id: string) {
    setIsNew(false);
    setSel(id);
    setForm(personas[id]);
  }

  async function run(fn: () => Promise<unknown>, ok: string) {
    setBusy(true);
    try {
      await fn();
      toast(ok);
      await reload();
    } catch (e) {
      toast(explainError(e), true);
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    const id = isNew ? slug(form.name) : sel!;
    if (!id) return toast("Give the persona a name first.", true);
    if (isNew && personas[id]) return toast("A persona with that name already exists.", true);
    await run(() => api.savePersona(id, form), "Persona saved");
    setIsNew(false);
    setSel(id);
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Personas</h1>
          <p>The character who chats with your customers. A new voice applies from the next customer message.</p>
        </div>
        <button
          className="btn dark"
          onClick={() => {
            setIsNew(true);
            setSel(null);
            setForm(BLANK);
          }}
        >
          New persona
        </button>
      </div>

      {error != null && !data && <div className="alert">{explainError(error)}</div>}
      {loading && !data && <div className="empty">Loading personas…</div>}

      <div className="cards">
        {Object.entries(personas).map(([id, p], i) => (
          <button key={id} className="persona-card" aria-pressed={sel === id && !isNew} onClick={() => pick(id)}>
            <span className="swatch" style={{ "--c": COLORS[i % COLORS.length] } as React.CSSProperties}>{p.name}</span>
            <span className="label">
              <span>{p.style.slice(0, 90)}{p.style.length > 90 ? "…" : ""}</span>
              {id === active && <span className="status-chip approved">Active</span>}
            </span>
          </button>
        ))}
      </div>

      {(sel || isNew) && (
        <div className="edit-grid">
          <section className="panel form">
            <h2>{isNew ? "New persona" : `Edit ${personas[sel!]?.name ?? ""}`}</h2>
            {FIELDS.map((f) => {
              const len = form[f.key].length;
              const lim = PERSONA_LIMITS[f.key];
              return (
                <label className="field" key={f.key}>
                  <span>{f.label}</span>
                  {f.area ? (
                    <textarea
                      className="textarea"
                      value={form[f.key]}
                      onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                    />
                  ) : (
                    <input
                      className="input"
                      value={form[f.key]}
                      onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                    />
                  )}
                  <small>{f.hint}</small>
                  <span className={`counter num${len > lim ? " over" : ""}`}>{len} / {lim}</span>
                </label>
              );
            })}
            <div className="modal-actions" style={{ justifyContent: "flex-start" }}>
              <button className="btn primary" disabled={busy || over || empty} onClick={save}>Save persona</button>
              {!isNew && sel !== active && (
                <button className="btn" disabled={busy} onClick={() => run(() => api.setActivePersona(sel!), "Persona is now active")}>
                  Make active
                </button>
              )}
            </div>
          </section>

          <aside className="phone" aria-label="Preview">
            <div className="who">{form.name || "Name"}</div>
            <div className="m">{fill(form.greeting, form) || "Greeting appears here."}</div>
            <div className="m me">Hi, I need a quote.</div>
            <div className="m">{fill(form.service_question, form) || "First question appears here."}</div>
            <div className="m me">My kitchen sink is leaking.</div>
            <div className="m">{fill(form.closing, form) || "Closing appears here."}</div>
            <small style={{ color: "#5b5348", marginTop: 6 }}>Preview. The server fills in your real business and owner names.</small>
          </aside>
        </div>
      )}
    </>
  );
}



