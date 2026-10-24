import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, explainError } from "@shared/api";
import { googleCalendarUrl } from "@shared/gcal";
import { money, slotLabel } from "@shared/format";
import { findConflicts } from "@shared/params";
import type { Booking, Interval, QuoteItem, Slot } from "@shared/types";
import { loadAllQuotes } from "../data";
import { gList, gRemove, gSync, useGoogle } from "../google";
import { useAsync } from "../hooks";
import { Modal } from "../ui/Modal";
import { StatusChip } from "../ui/StatusChip";
import { useToast } from "../ui/Toast";

type View = "month" | "week" | "day";
const H0 = 8;
const H1 = 20;
const HOUR_PX = 56;

const addDays = (d: Date, n: number) => {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
};
const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const startOfWeek = (d: Date) => addDays(startOfDay(d), -((d.getDay() + 6) % 7));
const sameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString();
const pad = (n: number) => String(n).padStart(2, "0");
const dateInput = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const timeInput = (d: Date) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
const combine = (date: string, time: string) => new Date(`${date}T${time}:00`);
const hoursOf = (i: Interval) => (new Date(i.end).getTime() - new Date(i.start).getTime()) / 3_600_000;
const dayLabel = (iso: string) => new Date(iso).toLocaleDateString("en-MY", { weekday: "short", day: "numeric", month: "short" });

function range(view: View, anchor: Date): { from: Date; to: Date; days: Date[] } {
  if (view === "day") {
    const f = startOfDay(anchor);
    return { from: f, to: addDays(f, 1), days: [f] };
  }
  if (view === "week") {
    const f = startOfWeek(anchor);
    return { from: f, to: addDays(f, 7), days: Array.from({ length: 7 }, (_, i) => addDays(f, i)) };
  }
  const f = startOfWeek(new Date(anchor.getFullYear(), anchor.getMonth(), 1));
  return { from: f, to: addDays(f, 42), days: Array.from({ length: 42 }, (_, i) => addDays(f, i)) };
}

function title(view: View, anchor: Date) {
  if (view === "month") return anchor.toLocaleDateString("en-MY", { month: "long", year: "numeric" });
  if (view === "day") return anchor.toLocaleDateString("en-MY", { weekday: "long", day: "numeric", month: "long" });
  const { days } = range("week", anchor);
  const f = days[0];
  const l = days[6];
  return `${f.toLocaleDateString("en-MY", { day: "numeric", month: "short" })} – ${l.toLocaleDateString("en-MY", { day: "numeric", month: "short", year: "numeric" })}`;
}

interface Draft {
  user_id?: string;
  date: string;
  time: string;
  hours?: number;
}

type FetchEvents = (fromIso: string, toIso: string) => Promise<Booking[]>;
type FetchSlots = (userId: string) => Promise<Slot[]>;

export default function Calendar() {
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const [view, setView] = useState<View>("week");
  const [anchor, setAnchor] = useState(() => new Date());
  const [creating, setCreating] = useState<Draft | null>(null);
  const [editing, setEditing] = useState<Booking | null>(null);
  const [suggestFor, setSuggestFor] = useState("");
  const jump = useRef(false);

  const r = useMemo(() => range(view, anchor), [view, anchor]);
  const bookings = useAsync(() => api.listBookings(r.from.toISOString(), r.to.toISOString()), [r.from.getTime(), r.to.getTime()]);
  const quotes = useAsync(loadAllQuotes, []);
  const g = useGoogle();
  const ext = useAsync(
    () => (g.connected ? gList(r.from.toISOString(), r.to.toISOString()) : Promise.resolve([] as Booking[])),
    [r.from.getTime(), r.to.getTime(), g.connected],
  );

  const busy: Interval[] = (ext.data ?? []).map((e) => ({ start: e.start, end: e.end, label: e.customer }));
  const fetchSlots: FetchSlots = (uid) => api.suggestSlots(uid, busy);
  const slots = useAsync(() => (suggestFor ? fetchSlots(suggestFor) : Promise.resolve([] as Slot[])), [suggestFor, g.connected, ext.data?.length ?? 0]);

  // Events for any day, so the guard also works for days outside the visible range.
  const fetchEvents: FetchEvents = async (a, b) => [...(await api.listBookings(a, b)), ...(g.connected ? await gList(a, b) : [])];

  async function mirror(b: Booking, remove = false) {
    if (!g.connected) return;
    try {
      if (remove) await gRemove(b.id);
      else await gSync(b);
      await ext.reload();
    } catch (e) {
      toast(`Saved here, but Google Calendar was not updated. ${(e as Error).message}`, true);
    }
  }

  // Arrive from a quote: show suggested times for that customer.
  const bookFor = params.get("book");
  useEffect(() => {
    if (bookFor) {
      setSuggestFor(bookFor);
      jump.current = true;
      setParams({}, { replace: true });
    }
  }, [bookFor]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (jump.current && slots.data && slots.data.length) {
      setAnchor(new Date(slots.data[0].start));
      jump.current = false;
    }
  }, [slots.data]);

  const openSlot = (s: Slot) =>
    setCreating({ user_id: suggestFor, date: dateInput(new Date(s.start)), time: timeInput(new Date(s.start)), hours: hoursOf(s) });

  const shift = (dir: number) =>
    setAnchor((a) => (view === "month" ? new Date(a.getFullYear(), a.getMonth() + dir, 1) : addDays(a, dir * (view === "week" ? 7 : 1))));

  const list = [...(bookings.data ?? []), ...(ext.data ?? [])];
  const today = new Date();
  const picked = (quotes.data ?? []).find((q) => q.user_id === suggestFor);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Calendar</h1>
          <p>Click an empty slot to book, or a job to move or cancel it. Bookings stay in this browser until the backend adds a bookings service.</p>
        </div>
        <button className="btn dark" onClick={() => setCreating({ date: dateInput(anchor), time: "09:00" })}>New booking</button>
      </div>

      <section className="panel suggest" aria-label="Suggested times">
        <div className="panel-title">
          <h2>Suggested times</h2>
          <label className="field inline">
            <span className="sr">Customer</span>
            <select className="select" value={suggestFor} onChange={(e) => { setSuggestFor(e.target.value); jump.current = true; }}>
              <option value="">Pick a customer</option>
              {(quotes.data ?? []).map((q) => (
                <option key={q.user_id} value={q.user_id}>{q.job.name ?? q.user_id}</option>
              ))}
            </select>
          </label>
        </div>
        {!suggestFor && <p className="muted">Pick a customer and Gesir suggests times that fit the job length and do not clash with anything on your calendar.</p>}
        {suggestFor && slots.loading && <p className="muted">Finding times…</p>}
        {suggestFor && slots.error != null && <div className="alert" role="alert">{explainError(slots.error)}<button className="btn small" onClick={slots.reload}>Try again</button></div>}
        {suggestFor && !slots.loading && slots.data && slots.data.length === 0 && <p className="muted">No free window found in the next two weeks. Book by hand, or free up some time.</p>}
        {slots.data && slots.data.length > 0 && (
          <>
            <p className="muted">For {picked?.job.name ?? "this customer"}: about {hoursOf(slots.data[0])} h on site{picked?.job.preferred_datetime ? `. They asked for: ${picked.job.preferred_datetime}.` : "."}</p>
            <div className="slots">
              {slots.data.map((s, i) => (
                <button key={s.start} className={`slot${i === 0 ? " best" : ""}`} onClick={() => openSlot(s)}>
                  <b>{dayLabel(s.start)}</b>
                  <span className="num">{slotLabel(s.start, s.end)}</span>
                  <small>{s.reason}</small>
                  {i === 0 && <em>Best fit</em>}
                </button>
              ))}
            </div>
          </>
        )}
      </section>

      <section className="panel gpanel">
        <div>
          <b>Google Calendar</b>
          <p>
            {g.connected
              ? g.mode === "demo"
                ? "Connected in demo mode. Sample Google events show in grey and nothing leaves this browser."
                : "Connected. Your other events show in grey, and bookings made here are copied to your calendar."
              : g.mode === "off"
                ? "Not set up. Add VITE_GOOGLE_CLIENT_ID to the web .env to turn this on."
                : "Connect to see your other events here and copy new bookings to your calendar."}
          </p>
        </div>
        {g.connected ? (
          <button className="btn small" onClick={() => g.disconnect()}>Disconnect</button>
        ) : (
          <button
            className="btn small primary"
            disabled={g.mode === "off"}
            onClick={() => g.connect().catch((e: Error) => toast(e.message, true))}
          >
            Connect Google Calendar
          </button>
        )}
      </section>

      <div className="cal-bar">
        <div className="cal-nav">
          <button className="btn small" onClick={() => shift(-1)} aria-label="Previous">‹</button>
          <button className="btn small" onClick={() => setAnchor(new Date())}>Today</button>
          <button className="btn small" onClick={() => shift(1)} aria-label="Next">›</button>
          <span className="cal-title">{title(view, anchor)}</span>
        </div>
        <div className="tabs" role="tablist" aria-label="Calendar view">
          {(["month", "week", "day"] as View[]).map((v) => (
            <button key={v} role="tab" className="tab" aria-selected={view === v} onClick={() => setView(v)}>
              {v[0].toUpperCase() + v.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {bookings.error != null && !bookings.data && <div className="alert">{explainError(bookings.error)}</div>}

      {view === "month" ? (
        <div className="grid-month">
          {r.days.slice(0, 7).map((d) => (
            <div className="dow" key={d.getDay()}>{d.toLocaleDateString("en-MY", { weekday: "short" })}</div>
          ))}
          {r.days.map((d) => {
            const evs = list.filter((b) => sameDay(new Date(b.start), d)).sort((a, b) => a.start.localeCompare(b.start));
            const sug = (slots.data ?? []).filter((s) => sameDay(new Date(s.start), d));
            return (
              <div
                key={d.toISOString()}
                className={`day${d.getMonth() !== anchor.getMonth() ? " dim" : ""}${sameDay(d, today) ? " today" : ""}`}
                onClick={() => setCreating({ date: dateInput(d), time: "09:00" })}
              >
                <button
                  className="d"
                  style={{ border: 0, background: "none" }}
                  aria-label={`Book on ${d.toDateString()}`}
                  onClick={(e) => { e.stopPropagation(); setCreating({ date: dateInput(d), time: "09:00" }); }}
                >
                  {d.getDate()}
                </button>
                {sug.map((s) => (
                  <button key={s.start} className="ev suggest" onClick={(e) => { e.stopPropagation(); openSlot(s); }}>
                    AI {timeInput(new Date(s.start))}
                  </button>
                ))}
                {evs.slice(0, 3).map((b) => (
                  <button key={b.id} className={`ev ${b.source ?? b.status}`} onClick={(e) => { e.stopPropagation(); setEditing(b); }}>
                    {timeInput(new Date(b.start))} {b.customer}
                  </button>
                ))}
                {evs.length > 3 && <span className="more">+{evs.length - 3} more</span>}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="timegrid">
          <div style={{ minWidth: view === "week" ? 720 : 0 }}>
            <div className="tg-head" style={{ gridTemplateColumns: `56px repeat(${r.days.length}, 1fr)` }}>
              <div />
              {r.days.map((d) => (
                <div key={d.toISOString()} className={sameDay(d, today) ? "today" : ""}>
                  {d.toLocaleDateString("en-MY", { weekday: "short", day: "numeric" })}
                </div>
              ))}
            </div>
            <div className="tg-body" style={{ gridTemplateColumns: `56px repeat(${r.days.length}, 1fr)` }}>
              <div className="tg-hours">
                {Array.from({ length: H1 - H0 }, (_, i) => (
                  <div key={i}>{new Date(2000, 0, 1, H0 + i).toLocaleTimeString("en-MY", { hour: "numeric", hour12: true })}</div>
                ))}
              </div>
              {r.days.map((d) => (
                <div className="tg-col" key={d.toISOString()}>
                  {Array.from({ length: H1 - H0 }, (_, i) => (
                    <button
                      key={i}
                      className="tg-cell"
                      aria-label={`Book ${d.toDateString()} ${H0 + i}:00`}
                      onClick={() => setCreating({ date: dateInput(d), time: `${pad(H0 + i)}:00` })}
                    />
                  ))}
                  {(slots.data ?? [])
                    .filter((s) => sameDay(new Date(s.start), d))
                    .map((s) => {
                      const st = new Date(s.start);
                      const top = Math.max(0, (st.getHours() + st.getMinutes() / 60 - H0) * HOUR_PX);
                      return (
                        <button key={s.start} className="tg-ev suggest" style={{ top, height: Math.max(28, hoursOf(s) * HOUR_PX - 2) }} onClick={() => openSlot(s)}>
                          <b>AI suggests</b>
                          {slotLabel(s.start, s.end)}
                        </button>
                      );
                    })}
                  {list
                    .filter((b) => sameDay(new Date(b.start), d))
                    .map((b) => {
                      const s = new Date(b.start);
                      const e = new Date(b.end);
                      const top = Math.max(0, (s.getHours() + s.getMinutes() / 60 - H0) * HOUR_PX);
                      const h = Math.max(28, ((e.getTime() - s.getTime()) / 3_600_000) * HOUR_PX - 2);
                      return (
                        <button key={b.id} className={`tg-ev ${b.source ?? b.status}`} style={{ top, height: h }} onClick={() => setEditing(b)}>
                          <b>{b.customer}</b>
                          {slotLabel(b.start, b.end)}
                        </button>
                      );
                    })}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {creating && (
        <CreateDialog
          draft={creating}
          quotes={quotes.data ?? []}
          fetchEvents={fetchEvents}
          fetchSlots={fetchSlots}
          onClose={() => setCreating(null)}
          onSaved={async (b) => {
            setCreating(null);
            toast("Booking saved");
            await bookings.reload();
            await mirror(b);
          }}
        />
      )}
      {editing && (
        <EditDialog
          b={editing}
          fetchEvents={fetchEvents}
          onClose={() => setEditing(null)}
          synced={g.connected}
          onSaved={async (msg, b, remove) => {
            setEditing(null);
            toast(msg);
            await bookings.reload();
            if (b) await mirror(b, remove);
          }}
        />
      )}
    </>
  );
}

const DURATIONS = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 12];
const hoursLabel = (h: number) => `${h} ${h === 1 ? "hour" : "hours"}`;

/** Events that clash with the chosen window. Loads the chosen day itself, so any date is covered. */
function useConflicts(date: string, time: string, hours: number, fetchEvents: FetchEvents, ignoreId?: string) {
  const [events, setEvents] = useState<Booking[]>([]);
  useEffect(() => {
    let live = true;
    const from = combine(date, "00:00");
    if (Number.isNaN(from.getTime())) return;
    fetchEvents(from.toISOString(), addDays(from, 1).toISOString()).then((e) => live && setEvents(e)).catch(() => {});
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date]);
  const start = combine(date, time);
  if (Number.isNaN(start.getTime())) return [];
  const win = { start: start.toISOString(), end: new Date(start.getTime() + hours * 3_600_000).toISOString() };
  return findConflicts(win, events.filter((e) => e.status !== "cancelled"), ignoreId) as Booking[];
}

function Guard({ conflicts, onNext }: { conflicts: Booking[]; onNext?: () => void }) {
  if (conflicts.length === 0) return null;
  return (
    <div className="guard" role="alert">
      <b>This time clashes with another event</b>
      <ul>
        {conflicts.map((c) => (
          <li key={c.id}>
            {c.customer}, <span className="num">{slotLabel(c.start, c.end)}</span>{c.source === "google" ? " (Google Calendar)" : ""}
          </li>
        ))}
      </ul>
      {onNext && <button type="button" className="btn small" onClick={onNext}>Use next free time</button>}
    </div>
  );
}

function CreateDialog({ draft, quotes, fetchEvents, fetchSlots, onClose, onSaved }: {
  draft: Draft; quotes: QuoteItem[]; fetchEvents: FetchEvents; fetchSlots: FetchSlots; onClose: () => void; onSaved: (b: Booking) => void;
}) {
  const [uid, setUid] = useState(draft.user_id ?? "");
  const [date, setDate] = useState(draft.date);
  const [time, setTime] = useState(draft.time);
  const [hours, setHours] = useState(draft.hours ?? 2);
  const [touched, setTouched] = useState(draft.hours != null);
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [sug, setSug] = useState<Slot[]>([]);

  const q = quotes.find((x) => x.user_id === uid);
  const customer = q ? q.job.name ?? q.user_id : name;
  const addr = q ? q.job.address ?? "" : address;
  const conflicts = useConflicts(date, time, hours, fetchEvents);

  useEffect(() => {
    if (!uid) return setSug([]);
    let live = true;
    fetchSlots(uid).then((s) => {
      if (!live) return;
      setSug(s);
      if (!touched && s[0]) setHours(hoursOf(s[0]));
    }).catch(() => live && setSug([]));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uid]);

  const use = (s: Slot) => {
    setDate(dateInput(new Date(s.start)));
    setTime(timeInput(new Date(s.start)));
    setHours(hoursOf(s));
    setTouched(true);
  };
  const next = sug.find((s) => findConflicts({ start: s.start, end: s.end }, [{ start: combine(date, time).toISOString(), end: new Date(combine(date, time).getTime() + hours * 3_600_000).toISOString() }]).length === 0) ?? sug[0];

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      const s = combine(date, time);
      const created = await api.createBooking({
        user_id: uid || `manual_${Date.now()}`,
        customer,
        phone: q?.job.phone,
        address: addr,
        start: s.toISOString(),
        end: new Date(s.getTime() + hours * 3_600_000).toISOString(),
      });
      onSaved(created);
    } catch (e) {
      setErr(e);
      setBusy(false);
    }
  }

  return (
    <Modal title="Book a slot" onClose={onClose}>
      <div className="form">
        <label className="field">
          <span>Customer</span>
          <select className="select" value={uid} onChange={(e) => setUid(e.target.value)}>
            <option value="">Someone else</option>
            {quotes.map((x) => (
              <option key={x.user_id} value={x.user_id}>{x.job.name ?? x.user_id}</option>
            ))}
          </select>
        </label>
        {!q && (
          <>
            <label className="field"><span>Name</span><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></label>
            <label className="field"><span>Address</span><input className="input" value={address} onChange={(e) => setAddress(e.target.value)} /></label>
          </>
        )}
        {q?.job.preferred_datetime && (
          <div className="hint">Customer asked for: <b>{q.job.preferred_datetime}</b></div>
        )}
        {sug.length > 0 && (
          <div className="field">
            <span>Suggested by Gesir</span>
            <div className="chip-row">
              {sug.slice(0, 4).map((s) => (
                <button key={s.start} type="button" className="fchip" onClick={() => use(s)}>
                  {dayLabel(s.start)} <small className="num">{timeInput(new Date(s.start))}</small>
                </button>
              ))}
            </div>
          </div>
        )}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <label className="field"><span>Date</span><input type="date" className="input" value={date} onChange={(e) => setDate(e.target.value)} /></label>
          <label className="field"><span>Start</span><input type="time" step={900} className="input" value={time} onChange={(e) => setTime(e.target.value)} /></label>
        </div>
        <label className="field">
          <span>Length</span>
          <select className="select" value={hours} onChange={(e) => { setHours(Number(e.target.value)); setTouched(true); }}>
            {[...new Set([...DURATIONS, hours])].sort((a, b) => a - b).map((h) => <option key={h} value={h}>{hoursLabel(h)}</option>)}
          </select>
        </label>
        <Guard conflicts={conflicts} onNext={next ? () => use(next) : undefined} />
        {err != null && <div className="alert">{explainError(err)}</div>}
      </div>
      <div className="modal-actions">
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn primary" disabled={busy || conflicts.length > 0 || !customer.trim() || !date || !time} onClick={save}>
          {busy ? "Saving…" : conflicts.length ? "Time is taken" : "Confirm booking"}
        </button>
      </div>
    </Modal>
  );
}

function EditDialog({ b, synced, fetchEvents, onClose, onSaved }: {
  b: Booking; synced: boolean; fetchEvents: FetchEvents; onClose: () => void; onSaved: (msg: string, b?: Booking, remove?: boolean) => void;
}) {
  const s0 = new Date(b.start);
  const hours0 = Math.max(0.5, Math.round(hoursOf(b) * 2) / 2);
  const [date, setDate] = useState(dateInput(s0));
  const [time, setTime] = useState(timeInput(s0));
  const [hours, setHours] = useState(hours0);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const conflicts = useConflicts(date, time, hours, fetchEvents, b.id);

  async function run(fn: () => Promise<unknown>, msg: string, remove = false) {
    setBusy(true);
    setErr(null);
    try {
      const res = await fn();
      onSaved(msg, (res as Booking | undefined) ?? b, remove);
    } catch (e) {
      setErr(e);
      setBusy(false);
    }
  }

  const cancelled = b.status === "cancelled";

  if (b.source === "google") {
    return (
      <Modal title={b.customer} onClose={onClose}>
        <p>{slotLabel(b.start, b.end)} · {new Date(b.start).toLocaleDateString("en-MY", { weekday: "long", day: "numeric", month: "long" })}</p>
        <p style={{ color: "var(--ink-2)" }}>This event is on your Google Calendar. Change it there.</p>
        <div className="modal-actions">
          <button className="btn" onClick={onClose}>Close</button>
          {b.link && <a className="btn primary" href={b.link} target="_blank" rel="noreferrer">Open in Google Calendar</a>}
        </div>
      </Modal>
    );
  }

  return (
    <Modal title={b.customer} onClose={onClose}>
      <div className="form">
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <StatusChip status={b.status} />
          <StatusChip status={b.quote_status} />
          {b.quote_total != null && <b className="num">{money(b.quote_total)}</b>}
        </div>
        <p>{b.address}</p>
        {!cancelled && (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <label className="field"><span>Date</span><input type="date" className="input" value={date} onChange={(e) => setDate(e.target.value)} /></label>
              <label className="field"><span>Start</span><input type="time" step={900} className="input" value={time} onChange={(e) => setTime(e.target.value)} /></label>
            </div>
            <label className="field">
              <span>Length</span>
              <select className="select" value={hours} onChange={(e) => setHours(Number(e.target.value))}>
                {[...new Set([...DURATIONS, hours0])].sort((a, c) => a - c).map((h) => <option key={h} value={h}>{hoursLabel(h)}</option>)}
              </select>
            </label>
            <Guard conflicts={conflicts} />
          </>
        )}
        {err != null && <div className="alert">{explainError(err)}</div>}
      </div>
      <div className="modal-actions">
        <button className="btn" onClick={onClose}>Close</button>
        {!cancelled && !synced && (
          <a
            className="btn"
            target="_blank"
            rel="noreferrer"
            href={googleCalendarUrl({ title: `${b.customer} (Gesir)`, start: b.start, end: b.end, location: b.address, details: b.phone ? `WhatsApp: +${b.phone}` : "" })}
          >
            Add to Google Calendar
          </a>
        )}
        {cancelled ? (
          <button className="btn danger" disabled={busy} onClick={() => run(() => api.deleteBooking(b.id), "Booking removed", true)}>Remove from calendar</button>
        ) : (
          <>
            <button className="btn danger" disabled={busy} onClick={() => run(() => api.updateBooking(b.id, { status: "cancelled" }), "Booking cancelled", true)}>
              Cancel booking
            </button>
            <button
              className="btn primary"
              disabled={busy || conflicts.length > 0}
              onClick={() => {
                const s = combine(date, time);
                run(
                  () => api.updateBooking(b.id, { start: s.toISOString(), end: new Date(s.getTime() + hours * 3_600_000).toISOString() }),
                  "Booking moved",
                );
              }}
            >
              {conflicts.length ? "Time is taken" : "Save changes"}
            </button>
          </>
        )}
      </div>
    </Modal>
  );
}
