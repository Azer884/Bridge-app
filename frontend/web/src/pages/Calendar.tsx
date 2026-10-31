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
import { holidaysOn } from "@shared/holidays";
import { Modal } from "../ui/Modal";
import { StatusChip } from "../ui/StatusChip";
import { useToast } from "../ui/Toast";

type View = "month" | "week" | "day";
const H0 = 8;
const H1 = 19;
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
  const [view, setView] = useState<View>("month");
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

  // Orbyte's leave calendar shows Monday to Friday only, and only the weeks of the month
  const weekdays = r.days.filter((d) => d.getDay() % 6 !== 0);
  const monthCells = view === "month"
    ? weekdays.filter((_, i) => weekdays.slice(Math.floor(i / 5) * 5, Math.floor(i / 5) * 5 + 5).some((x) => x.getMonth() === anchor.getMonth()))
    : [];
  const cells = monthCells;
  const cols = 5;

  return (
    <div className="ob-cal-page">

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

      <section className="ob-cal ob-card ob-first">
      <div className="ob-cal-head">
        <h1>Job Calendar</h1>
        <div className="ob-cal-nav">
          <button className="ob-icon" onClick={() => shift(-1)} aria-label="Previous">‹</button>
          <b>{title(view, anchor)}</b>
          <button className="ob-icon" onClick={() => shift(1)} aria-label="Next">›</button>
        </div>
      </div>
      <div className="ob-cal-tools">
        <div className="ob-tabs" role="tablist" aria-label="Calendar view">
          {(["month", "week", "day"] as View[]).map((v) => (
            <button key={v} role="tab" aria-selected={view === v} className={`ob-tab${view === v ? " on" : ""}`} onClick={() => setView(v)}>
              {v[0].toUpperCase() + v.slice(1)}
            </button>
          ))}
        </div>
        <button className="btn small" onClick={() => setAnchor(new Date())}>Today</button>
        <button className="btn small primary" onClick={() => setCreating({ date: dateInput(anchor), time: "09:00" })}>New booking</button>
      </div>

      {bookings.error != null && !bookings.data && <div className="alert">{explainError(bookings.error)}</div>}

      {view === "month" ? (
        <div className={`grid-month ob-month ob-${view}`} style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
          {weekdays.slice(0, 5).map((d) => (
            <div className="dow" key={d.getDay()}>{d.toLocaleDateString("en-GB", { weekday: "short" }).toUpperCase()}</div>
          ))}
          {cells.map((d) => {
            const hols = holidaysOn(dateInput(d));
            const evs = list.filter((b) => sameDay(new Date(b.start), d)).sort((a, b) => a.start.localeCompare(b.start));
            const sug = (slots.data ?? []).filter((s) => sameDay(new Date(s.start), d));
            return (
              <div
                key={d.toISOString()}
                className={`day${d.getMonth() !== anchor.getMonth() ? " dim" : ""}${sameDay(d, today) ? " today" : ""}${hols.length ? " holiday" : ""}`}
                onClick={() => !hols.length && setCreating({ date: dateInput(d), time: "09:00" })}
              >
                <button
                  className="d"
                  style={{ border: 0, background: "none" }}
                  aria-label={`Book on ${d.toDateString()}`}
                  onClick={(e) => { e.stopPropagation(); setCreating({ date: dateInput(d), time: "09:00" }); }}
                >
                  {d.getDate()}
                </button>
                {hols.map((h) => (
                  <span key={h.country + h.name} className="ob-holiday" title="Public holiday: no jobs are booked">{h.country} • {h.name}</span>
                ))}
                {sug.map((s) => (
                  <button key={s.start} className="ev suggest" onClick={(e) => { e.stopPropagation(); openSlot(s); }}>
                    AI {timeInput(new Date(s.start))}
                  </button>
                ))}
                {evs.slice(0, view === "month" ? 3 : 20).map((b) => (
                  <button key={b.id} className={`ev ${b.source ?? b.status}`} onClick={(e) => { e.stopPropagation(); setEditing(b); }}>
                    {timeInput(new Date(b.start))} {b.customer}
                  </button>
                ))}
                {view === "month" && evs.length > 3 && <span className="more">+{evs.length - 3} more</span>}
              </div>
            );
          })}
        </div>
      ) : (
        <TimeGrid
          days={view === "week" ? weekdays : r.days}
          events={list}
          suggestions={slots.data ?? []}
          onSlot={(d, time) => setCreating({ date: dateInput(d), time })}
          onEvent={setEditing}
          onSuggest={openSlot}
        />
      )}
      </section>

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
    </div>
  );
}

// One booking is one working day at most: 9 am to 6 pm with lunch from 1 to 2 pm (as in src/calendar_scheduler.py).
// A longer job gets one booking per day.
const DURATIONS = [1, 1.5, 2, 2.5, 3, 3.5, 4, 5, 6, 7, 8];
const hoursLabel = (h: number) => `${h} ${h === 1 ? "hour" : "hours"}`;
const DAY_START = 9, LUNCH_START = 13, LUNCH_END = 14, DAY_END = 18;
const hourOf = (time: string) => { const [h, m] = time.split(":").map(Number); return h + (m || 0) / 60; };
const clockOf = (h: number) => `${h % 12 === 0 ? 12 : Math.floor(h % 12)}${h % 1 ? `:${pad(Math.round((h % 1) * 60))}` : ""} ${h < 12 ? "am" : "pm"}`;

/** When a job of `hours` working hours that starts at `start` ends on the clock: the lunch hour is skipped, not worked.
 * null when it does not fit in the working day. */
function endOf(start: number, hours: number): number | null {
  if (start < DAY_START || start >= DAY_END || (start >= LUNCH_START && start < LUNCH_END)) return null;
  let end = start + hours;
  if (start < LUNCH_START && end > LUNCH_START) end += LUNCH_END - LUNCH_START;
  return end <= DAY_END ? end : null;
}
const fits = (time: string) => DURATIONS.filter((h) => endOf(hourOf(time), h) != null);

/** Why this day and start cannot be booked, in plain words; null when they can. */
function workProblem(date: string, time: string, hours: number): string | null {
  const day = combine(date, "12:00");
  if (Number.isNaN(day.getTime()) || !time) return null;
  if (day.getDay() % 6 === 0) return "The crew does not work at weekends. Pick a weekday.";
  const hol = holidaysOn(date)[0];
  if (hol) return `${hol.name} is a public holiday. Pick another day.`;
  const start = hourOf(time);
  if (start < DAY_START || start >= DAY_END) return "Start between 9 am and 6 pm.";
  if (start >= LUNCH_START && start < LUNCH_END) return "1 pm to 2 pm is lunch. Start before 1 pm or from 2 pm.";
  if (endOf(start, hours) == null) {
    const longest = fits(time).pop();
    return longest ? `That runs past 6 pm. From this start the longest job is ${hoursLabel(longest)}.` : "There is no time left in the day from this start.";
  }
  return null;
}

/** The clock end of the booking, with lunch skipped. */
function endAt(date: string, time: string, hours: number): Date {
  const start = hourOf(time);
  const end = endOf(start, hours) ?? start + hours;
  return combine(date, `${pad(Math.floor(end))}:${pad(Math.round((end % 1) * 60))}`);
}

/** Working hours of a booking already saved: its clock length minus the lunch hour when it spans lunch. */
function workHours(b: Interval): number {
  const s = new Date(b.start), e = new Date(b.end);
  const a = s.getHours() + s.getMinutes() / 60, z = e.getHours() + e.getMinutes() / 60;
  const lunch = a < LUNCH_START && z >= LUNCH_END ? LUNCH_END - LUNCH_START : 0;
  return Math.max(0.5, Math.round((hoursOf(b) - lunch) * 2) / 2);
}

function EndNote({ date, time, hours }: { date: string; time: string; hours: number }) {
  const start = hourOf(time);
  const end = endOf(start, hours);
  if (end == null || !date) return null;
  const lunch = start < LUNCH_START && end > LUNCH_START;
  return <p className="ob-endnote">Ends at <b>{clockOf(end)}</b>{lunch ? ". The lunch hour, 1 to 2 pm, is not counted." : "."}</p>;
}

function LengthSelect({ time, hours, onChange }: { time: string; hours: number; onChange: (h: number) => void }) {
  const ok = fits(time);
  const options = [...new Set([...(ok.length ? ok : DURATIONS), hours])].sort((a, b) => a - b);
  return (
    <select className="select" value={hours} onChange={(e) => onChange(Number(e.target.value))}>
      {options.map((h) => <option key={h} value={h} disabled={ok.length > 0 && !ok.includes(h)}>{hoursLabel(h)}</option>)}
    </select>
  );
}

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
  const win = { start: start.toISOString(), end: endAt(date, time, hours).toISOString() };
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
      if (!touched && s[0]) setHours(workHours(s[0]));
    }).catch(() => live && setSug([]));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uid]);

  const use = (s: Slot) => {
    setDate(dateInput(new Date(s.start)));
    setTime(timeInput(new Date(s.start)));
    setHours(workHours(s));
    setTouched(true);
  };
  const next = sug.find((s) => findConflicts({ start: s.start, end: s.end }, [{ start: combine(date, time).toISOString(), end: endAt(date, time, hours).toISOString() }]).length === 0) ?? sug[0];
  const problem = workProblem(date, time, hours);

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
        end: endAt(date, time, hours).toISOString(),
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
          <LengthSelect time={time} hours={hours} onChange={(h) => { setHours(h); setTouched(true); }} />
        </label>
        {problem ? <div className="ob-banner warn" role="alert">{problem}</div> : <EndNote date={date} time={time} hours={hours} />}
        <Guard conflicts={conflicts} onNext={next ? () => use(next) : undefined} />
        {err != null && <div className="alert">{explainError(err)}</div>}
      </div>
      <div className="modal-actions">
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn primary" disabled={busy || !!problem || conflicts.length > 0 || !customer.trim() || !date || !time} onClick={save}>
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
  const hours0 = workHours(b);
  const [date, setDate] = useState(dateInput(s0));
  const [time, setTime] = useState(timeInput(s0));
  const [hours, setHours] = useState(hours0);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const conflicts = useConflicts(date, time, hours, fetchEvents, b.id);
  const problem = workProblem(date, time, hours);

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
              <LengthSelect time={time} hours={hours} onChange={setHours} />
            </label>
            {problem ? <div className="ob-banner warn" role="alert">{problem}</div> : <EndNote date={date} time={time} hours={hours} />}
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
              disabled={busy || !!problem || conflicts.length > 0}
              onClick={() => {
                const s = combine(date, time);
                run(
                  () => api.updateBooking(b.id, { start: s.toISOString(), end: endAt(date, time, hours).toISOString() }),
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

/** Week and day views: an hour grid in the Orbyte style. Bookings sit at their real time and length; hours the crew does
 * not work (before 9, lunch, after 6), weekends and public holidays are hatched and cannot be booked. */
function TimeGrid({ days, events, suggestions, onSlot, onEvent, onSuggest }: {
  days: Date[];
  events: Booking[];
  suggestions: Slot[];
  onSlot: (d: Date, time: string) => void;
  onEvent: (b: Booking) => void;
  onSuggest: (s: Slot) => void;
}) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(id);
  }, []);
  const hours = Array.from({ length: H1 - H0 }, (_, i) => H0 + i);
  const at = (d: Date) => (d.getHours() + d.getMinutes() / 60 - H0) * HOUR_PX;
  const span = (a: string, b: string) => Math.max(((new Date(b).getTime() - new Date(a).getTime()) / 3_600_000) * HOUR_PX, 26);
  const label = (h: number) => `${h % 12 || 12} ${h < 12 ? "am" : "pm"}`;
  const off: [number, number][] = [[H0, 9], [13, 14], [18, H1]];       // before work, lunch, after work

  function pick(e: React.MouseEvent<HTMLDivElement>, d: Date) {
    const y = e.clientY - e.currentTarget.getBoundingClientRect().top;
    const mins = H0 * 60 + Math.floor((y / HOUR_PX) * 2) * 30;      // to the half hour
    onSlot(d, `${pad(Math.floor(mins / 60))}:${pad(mins % 60)}`);
  }

  return (
    <div className="ob-tg" style={{ "--cols": days.length } as React.CSSProperties}>
      <div className="ob-tg-head">
        <div className="ob-tg-corner" />
        {days.map((d) => (
          <div key={d.toISOString()} className={`ob-tg-day${sameDay(d, now) ? " today" : ""}`}>
            <span>{d.toLocaleDateString("en-GB", { weekday: days.length === 1 ? "long" : "short" })}</span>
            <b>{d.getDate()}</b>
          </div>
        ))}
      </div>
      <div className="ob-tg-body">
        <div className="ob-tg-gutter">
          {hours.map((h) => <div key={h} style={{ height: HOUR_PX }}><span>{label(h)}</span></div>)}
        </div>
        {days.map((d) => {
          const hols = holidaysOn(dateInput(d));
          const closed = hols.length > 0 || d.getDay() % 6 === 0;
          const evs = events.filter((b) => sameDay(new Date(b.start), d)).sort((a, b) => a.start.localeCompare(b.start));
          // side by side when two bookings overlap
          // a job that runs through lunch is drawn in two parts, so the lunch hour stays visible between them
          const l0 = new Date(d.getFullYear(), d.getMonth(), d.getDate(), LUNCH_START).getTime();
          const l1 = new Date(d.getFullYear(), d.getMonth(), d.getDate(), LUNCH_END).getTime();
          const parts = evs.flatMap((b) => {
            const s = new Date(b.start).getTime(), e = new Date(b.end).getTime();
            return s < l0 && e > l1
              ? [{ b, s, e: l0, part: 1 }, { b, s: l1, e, part: 2 }]
              : [{ b, s, e, part: 0 }];
          }).sort((x, y) => x.s - y.s);
          const lanes: number[] = [];
          const placed = parts.map((p) => {
            let lane = lanes.findIndex((end) => end <= p.s);
            if (lane < 0) lane = lanes.push(0) - 1;
            lanes[lane] = p.e;
            return { ...p, lane };
          });
          const width = 100 / Math.max(lanes.length, 1);
          return (
            <div key={d.toISOString()} className={`ob-tg-col${closed ? " closed" : ""}`} style={{ height: (H1 - H0) * HOUR_PX }}
              onClick={(e) => !closed && pick(e, d)} title={closed ? undefined : "Click to book this time"}>
              {hours.map((h) => <i key={h} className="ob-tg-line" style={{ top: (h - H0) * HOUR_PX }} />)}
              {!closed && off.map(([a, b]) => (
                <div key={a} className="ob-tg-off" style={{ top: (a - H0) * HOUR_PX, height: (b - a) * HOUR_PX }} onClick={(e) => e.stopPropagation()}>
                  {a === 13 && <span>Lunch</span>}
                </div>
              ))}
              {closed && (
                <div className="ob-tg-closed">
                  {hols.length ? hols.map((h) => <span key={h.name} className="ob-holiday">{h.country} • {h.name}</span>) : <span className="ob-holiday">Weekend</span>}
                  <small>No jobs are booked on this day.</small>
                </div>
              )}
              {!closed && suggestions.filter((s) => sameDay(new Date(s.start), d)).map((s) => (
                <button key={s.start} className="ob-tg-ev suggest" style={{ top: at(new Date(s.start)), height: span(s.start, s.end) }}
                  onClick={(e) => { e.stopPropagation(); onSuggest(s); }}>
                  <b>Suggested time</b><small>{slotLabel(s.start, s.end)}</small>
                </button>
              ))}
              {placed.map(({ b, s, e, part, lane }) => (
                <button key={`${b.id}-${part}`} className={`ob-tg-ev ${b.source ?? b.status}${part ? ` part${part}` : ""}`}
                  style={{ top: at(new Date(s)), height: span(new Date(s).toISOString(), new Date(e).toISOString()), left: `calc(${lane * width}% + 3px)`, width: `calc(${width}% - 6px)` }}
                  onClick={(ev) => { ev.stopPropagation(); onEvent(b); }}
                  aria-label={part === 2 ? `${b.customer}, after lunch` : undefined}>
                  <b>{b.customer}{part === 2 ? " (after lunch)" : ""}</b>
                  <small>
                    {part === 0
                      ? `${timeInput(new Date(b.start))} to ${timeInput(new Date(b.end))}${b.address ? `, ${b.address}` : ""}`
                      : `${timeInput(new Date(s))} to ${timeInput(new Date(e))}${part === 1 && b.address ? `, ${b.address}` : ""}`}
                  </small>
                </button>
              ))}
              {sameDay(d, now) && now.getHours() >= H0 && now.getHours() < H1 && <i className="ob-tg-now" style={{ top: at(now) }} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}
