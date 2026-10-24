import { useEffect, useMemo, useState } from "react";
import { Linking, Pressable, ScrollView, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useNavigation, useRoute } from "@react-navigation/native";
import { api, explainError } from "../../../shared/api";
import { money, slotLabel } from "../../../shared/format";
import { googleCalendarUrl } from "../../../shared/gcal";
import { findConflicts } from "../../../shared/params";
import type { Booking, Interval, QuoteItem, Slot } from "../../../shared/types";
import { loadAllQuotes } from "../data";
import { useAsync } from "../hooks";
import { C, useTheme } from "../theme";
import { Banner, Btn, Chip, Field, Group, Pill, Row, Screen, Segmented, Sheet, T, success } from "../ui";

type View_ = "month" | "week" | "day";
const addDays = (d: Date, n: number) => { const r = new Date(d); r.setDate(r.getDate() + n); return r; };
const sod = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const sow = (d: Date) => addDays(sod(d), -((d.getDay() + 6) % 7));
const same = (a: Date, b: Date) => a.toDateString() === b.toDateString();
const pad = (n: number) => String(n).padStart(2, "0");
const key = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const hhmm = (d: Date) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
const at = (date: string, time: string) => new Date(`${date}T${time}:00`);
const dayName = (d: Date) => d.toLocaleDateString("en-MY", { weekday: "short", day: "numeric", month: "short" });
const clock = (t: string) => at("2000-01-01", t).toLocaleTimeString("en-MY", { hour: "numeric", minute: "2-digit", hour12: true });
const hoursOf = (i: Interval) => (new Date(i.end).getTime() - new Date(i.start).getTime()) / 3_600_000;

function span(view: View_, a: Date) {
  if (view === "day") { const f = sod(a); return { from: f, to: addDays(f, 1) }; }
  if (view === "week") { const f = sow(a); return { from: f, to: addDays(f, 7) }; }
  const f = sow(new Date(a.getFullYear(), a.getMonth(), 1));
  return { from: f, to: addDays(f, 42) };
}

const TIMES = Array.from({ length: 21 }, (_, i) => `${pad(8 + Math.floor(i / 2))}:${i % 2 ? "30" : "00"}`);
const DURATIONS = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 12];

interface Draft { uid: string; date: string; time: string; hours?: number }

export default function CalendarScreen() {
  useTheme();
  const nav = useNavigation<any>();
  const route = useRoute<any>();
  const [view, setView] = useState<View_>("week");
  const [anchor, setAnchor] = useState(() => new Date());
  const [selected, setSelected] = useState(() => sod(new Date()));
  const [creating, setCreating] = useState<Draft | null>(null);
  const [editing, setEditing] = useState<Booking | null>(null);
  const [suggestFor, setSuggestFor] = useState("");
  const [picker, setPicker] = useState(false);
  const [jump, setJump] = useState(false);

  const { from, to } = useMemo(() => span(view, anchor), [view, anchor]);
  const bookings = useAsync(() => api.listBookings(from.toISOString(), to.toISOString()), [from.getTime(), to.getTime()]);
  const quotes = useAsync(loadAllQuotes, []);
  const slots = useAsync(() => (suggestFor ? api.suggestSlots(suggestFor) : Promise.resolve([] as Slot[])), [suggestFor]);
  const list = (bookings.data ?? []).slice().sort((a, b) => a.start.localeCompare(b.start));
  const sug = slots.data ?? [];
  const on = (d: Date) => list.filter((b) => same(new Date(b.start), d));
  const sugOn = (d: Date) => sug.filter((s) => same(new Date(s.start), d));
  const picked = (quotes.data ?? []).find((q) => q.user_id === suggestFor);

  // Arrive from a quote: show suggested times for that customer.
  const bookFor = route.params?.book as string | undefined;
  useEffect(() => {
    if (bookFor) {
      setSuggestFor(bookFor);
      setJump(true);
      nav.setParams({ book: undefined });
    }
  }, [bookFor]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (jump && sug.length) {
      const d = new Date(sug[0].start);
      setAnchor(d);
      setSelected(sod(d));
      setJump(false);
    }
  }, [sug, jump]);

  const shift = (n: number) =>
    setAnchor((a) => {
      const next = view === "month" ? new Date(a.getFullYear(), a.getMonth() + n, 1) : addDays(a, n * (view === "week" ? 7 : 1));
      if (view === "day") setSelected(sod(next));
      return next;
    });

  const heading =
    view === "month" ? anchor.toLocaleDateString("en-MY", { month: "long", year: "numeric" })
    : view === "day" ? dayName(anchor)
    : `${dayName(from)} to ${dayName(addDays(from, 6))}`;

  const openSlot = (s: Slot) => setCreating({ uid: suggestFor, date: key(new Date(s.start)), time: hhmm(new Date(s.start)), hours: hoursOf(s) });

  const bookingRow = (b: Booking) => (
    <Row
      key={b.id}
      left={<View style={{ width: 4, alignSelf: "stretch", borderRadius: 2, backgroundColor: b.status === "cancelled" ? C.ink3 : b.status === "tentative" ? C.tape : C.ok }} />}
      title={<T style={b.status === "cancelled" ? { textDecorationLine: "line-through", color: C.ink3 } : undefined}>{b.customer}</T>}
      subtitle={`${slotLabel(b.start, b.end)} · ${b.address}`}
      right={<Pill status={b.status} />}
      onPress={() => setEditing(b)}
    />
  );
  const slotRow = (s: Slot, i: number) => (
    <Row
      key={`s-${s.start}`}
      left={<Ionicons name="sparkles" size={18} color={C.ok} />}
      title={<T>AI suggests{i === 0 ? " · best fit" : ""}</T>}
      subtitle={`${slotLabel(s.start, s.end)} · ${s.reason}`}
      onPress={() => openSlot(s)}
    />
  );

  const dayBlock = (d: Date) => {
    const evs = on(d);
    const ss = sugOn(d);
    return (
      <View key={d.toISOString()} style={{ gap: 6 }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", paddingHorizontal: 16 }}>
          <T v="label" style={same(d, new Date()) ? { color: C.blue } : undefined}>{dayName(d)}</T>
          <Pressable accessibilityRole="button" accessibilityLabel={`Book on ${d.toDateString()}`} hitSlop={10} onPress={() => setCreating({ uid: suggestFor, date: key(d), time: "09:00" })}>
            <T v="label" style={{ color: C.blue }}>Book</T>
          </Pressable>
        </View>
        {evs.length + ss.length === 0 ? (
          <T v="foot" style={{ paddingHorizontal: 16 }}>Free</T>
        ) : (
          <Group>{[...ss.map((s) => slotRow(s, sug.indexOf(s))), ...evs.map(bookingRow)]}</Group>
        )}
      </View>
    );
  };

  const monthDays = view === "month" ? Array.from({ length: 42 }, (_, i) => addDays(from, i)) : [];

  return (
    <>
      <Screen>
        <Group title="Suggested times" footer={!suggestFor ? "Pick a customer. Gesir suggests times that fit the job length and do not clash with anything on your calendar." : undefined}>
          <Row title="Customer" value={picked?.job.name ?? "Pick a customer"} onPress={() => setPicker(true)} />
          {suggestFor && slots.loading ? <Row title="Finding times…" chevron={false} /> : null}
          {suggestFor && !slots.loading && sug.length === 0 && slots.error == null ? <Row title="No free window in the next two weeks" subtitle="Book by hand, or free up some time." chevron={false} /> : null}
          {sug.slice(0, 5).map(slotRow)}
        </Group>
        {slots.error != null && <Banner text={explainError(slots.error)} action="Try again" onAction={slots.reload} />}
        {picked?.job.preferred_datetime ? <T v="foot" style={{ paddingHorizontal: 16 }}>{picked.job.name} asked for: {picked.job.preferred_datetime}</T> : null}

        <View style={{ gap: 12 }}>
          <Segmented value={view} onChange={setView} options={[{ id: "month", label: "Month" }, { id: "week", label: "Week" }, { id: "day", label: "Day" }]} />
          <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
            <Pressable accessibilityRole="button" accessibilityLabel="Previous" onPress={() => shift(-1)} style={{ width: 44, height: 44, alignItems: "center", justifyContent: "center" }}><Ionicons name="chevron-back" size={22} color={C.blue} /></Pressable>
            <T v="headline" style={{ flex: 1, textAlign: "center" }}>{heading}</T>
            <Pressable accessibilityRole="button" accessibilityLabel="Next" onPress={() => shift(1)} style={{ width: 44, height: 44, alignItems: "center", justifyContent: "center" }}><Ionicons name="chevron-forward" size={22} color={C.blue} /></Pressable>
          </View>
          <View style={{ flexDirection: "row", gap: 8 }}>
            <View style={{ flex: 1 }}><Btn small kind="tinted" label="Today" onPress={() => { setAnchor(new Date()); setSelected(sod(new Date())); }} /></View>
            <View style={{ flex: 1 }}><Btn small kind="primary" icon="add" label="New booking" onPress={() => setCreating({ uid: suggestFor, date: key(selected), time: "09:00" })} /></View>
          </View>
        </View>
        {bookings.error != null && !bookings.data && <Banner text={explainError(bookings.error)} />}

        {view === "month" && (
          <>
            <View style={{ backgroundColor: C.paper, borderRadius: 16, padding: 8 }}>
              <View style={{ flexDirection: "row" }}>
                {["M", "T", "W", "T", "F", "S", "S"].map((l, i) => <T key={i} v="label" style={{ flex: 1, textAlign: "center" }}>{l}</T>)}
              </View>
              <View style={{ flexDirection: "row", flexWrap: "wrap" }}>
                {monthDays.map((d) => {
                  const n = on(d).length;
                  const hasSug = sugOn(d).length > 0;
                  const sel = same(d, selected);
                  const dim = d.getMonth() !== anchor.getMonth();
                  return (
                    <Pressable key={d.toISOString()} accessibilityRole="button" accessibilityLabel={`${d.toDateString()}, ${n} booked${hasSug ? ", suggested time" : ""}`} onPress={() => setSelected(sod(d))} style={{ width: `${100 / 7}%`, height: 50, alignItems: "center", justifyContent: "center" }}>
                      <View style={{ width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center", backgroundColor: sel ? C.blue : "transparent", borderWidth: hasSug && !sel ? 2 : 0, borderColor: C.ok, borderStyle: "dashed" }}>
                        <T style={{ color: sel ? C.white : dim ? C.ink3 : same(d, new Date()) ? C.blue : C.ink, fontWeight: same(d, new Date()) ? "700" : "400" }}>{d.getDate()}</T>
                      </View>
                      <View style={{ flexDirection: "row", gap: 2, height: 5 }}>
                        {Array.from({ length: Math.min(n, 3) }, (_, i) => <View key={i} style={{ width: 4, height: 4, borderRadius: 2, backgroundColor: C.ink3 }} />)}
                      </View>
                    </Pressable>
                  );
                })}
              </View>
            </View>
            {dayBlock(selected)}
          </>
        )}
        {view === "week" && Array.from({ length: 7 }, (_, i) => dayBlock(addDays(from, i)))}
        {view === "day" && dayBlock(anchor)}
      </Screen>

      <Sheet visible={picker} title="Customer" onClose={() => setPicker(false)}>
        <Group>
          <Row title="None" chevron={false} right={!suggestFor ? <Ionicons name="checkmark" size={22} color={C.blue} /> : undefined} onPress={() => { setSuggestFor(""); setPicker(false); }} />
          {(quotes.data ?? []).map((q) => (
            <Row key={q.user_id} title={q.job.name ?? q.user_id} subtitle={q.job.surfaces} chevron={false} right={suggestFor === q.user_id ? <Ionicons name="checkmark" size={22} color={C.blue} /> : undefined} onPress={() => { setSuggestFor(q.user_id); setJump(true); setPicker(false); }} />
          ))}
        </Group>
      </Sheet>

      <CreateSheet draft={creating} quotes={quotes.data ?? []} onClose={() => setCreating(null)} onSaved={async () => { setCreating(null); success(); await bookings.reload(); }} />
      <EditSheet b={editing} onClose={() => setEditing(null)} onSaved={async () => { setEditing(null); await bookings.reload(); }} />
    </>
  );
}

/** Events that clash with the chosen window. Loads that day itself, so any date is covered. */
function useConflicts(date: string, time: string, hours: number, ignoreId?: string) {
  const [events, setEvents] = useState<Booking[]>([]);
  useEffect(() => {
    let live = true;
    const f = at(date, "00:00");
    if (Number.isNaN(f.getTime())) return;
    api.listBookings(f.toISOString(), addDays(f, 1).toISOString()).then((e) => live && setEvents(e)).catch(() => {});
    return () => { live = false; };
  }, [date]);
  const start = at(date, time);
  if (Number.isNaN(start.getTime())) return [];
  const win = { start: start.toISOString(), end: new Date(start.getTime() + hours * 3_600_000).toISOString() };
  return findConflicts(win, events.filter((e) => e.status !== "cancelled"), ignoreId) as Booking[];
}

function Guard({ conflicts, onNext }: { conflicts: Booking[]; onNext?: () => void }) {
  if (conflicts.length === 0) return null;
  return (
    <View accessibilityRole="alert" style={{ backgroundColor: C.dangerWash, borderWidth: 2, borderColor: C.danger, borderRadius: 14, padding: 14, gap: 6 }}>
      <T v="headline" style={{ color: C.ink }}>This time clashes with another event</T>
      {conflicts.map((c) => <T key={c.id} v="sub" style={{ color: C.ink }}>{c.customer}, {slotLabel(c.start, c.end)}</T>)}
      {onNext ? <Btn small kind="tinted" label="Use next free time" onPress={onNext} /> : null}
    </View>
  );
}

function SlotPicker({ date, time, hours, setDate, setTime, setHours }: { date: string; time: string; hours: number; setDate: (s: string) => void; setTime: (s: string) => void; setHours: (n: number) => void }) {
  const dates = useMemo(() => {
    const base = Array.from({ length: 28 }, (_, i) => addDays(sod(new Date()), i));
    const extra = at(date, "00:00");
    return base.some((d) => key(d) === date) || Number.isNaN(extra.getTime()) ? base : [extra, ...base];
  }, [date]);
  return (
    <>
      <View style={{ gap: 6 }}>
        <T v="label">Date</T>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
          {dates.map((d) => <Chip key={key(d)} label={dayName(d)} on={key(d) === date} onPress={() => setDate(key(d))} />)}
        </ScrollView>
      </View>
      <View style={{ gap: 6 }}>
        <T v="label">Start</T>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          {TIMES.map((t) => <Chip key={t} label={clock(t)} on={t === time} onPress={() => setTime(t)} />)}
        </View>
      </View>
      <View style={{ gap: 6 }}>
        <T v="label">Length</T>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          {[...new Set([...DURATIONS, hours])].sort((a, b) => a - b).map((h) => <Chip key={h} label={`${h} h`} on={h === hours} onPress={() => setHours(h)} />)}
        </View>
      </View>
    </>
  );
}

function CreateSheet({ draft, quotes, onClose, onSaved }: { draft: Draft | null; quotes: QuoteItem[]; onClose: () => void; onSaved: () => void }) {
  const [uid, setUid] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("09:00");
  const [hours, setHours] = useState(2);
  const [touched, setTouched] = useState(false);
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [sug, setSug] = useState<Slot[]>([]);

  useEffect(() => {
    if (draft) { setUid(draft.uid); setDate(draft.date); setTime(draft.time); setHours(draft.hours ?? 2); setTouched(draft.hours != null); setErr(null); setBusy(false); }
  }, [draft]);

  useEffect(() => {
    if (!uid) { setSug([]); return; }
    let live = true;
    api.suggestSlots(uid).then((s) => {
      if (!live) return;
      setSug(s);
      if (!touched && s[0]) setHours(hoursOf(s[0]));
    }).catch(() => live && setSug([]));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uid]);

  const q = quotes.find((x) => x.user_id === uid);
  const customer = q ? q.job.name ?? q.user_id : name;
  const conflicts = useConflicts(date || key(new Date()), time, hours);
  const use = (s: Slot) => { setDate(key(new Date(s.start))); setTime(hhmm(new Date(s.start))); setHours(hoursOf(s)); setTouched(true); };
  const next = sug.find((s) => findConflicts({ start: s.start, end: s.end }, [{ start: at(date, time).toISOString(), end: new Date(at(date, time).getTime() + hours * 3_600_000).toISOString() }]).length === 0) ?? sug[0];

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      const s = at(date, time);
      await api.createBooking({ user_id: uid || `manual_${Date.now()}`, customer, phone: q?.job.phone, address: q ? q.job.address ?? "" : address, start: s.toISOString(), end: new Date(s.getTime() + hours * 3_600_000).toISOString() });
      onSaved();
    } catch (e) {
      setErr(e);
      setBusy(false);
    }
  }

  return (
    <Sheet visible={!!draft} title="Book a slot" onClose={onClose}>
      <View style={{ gap: 6 }}>
        <T v="label">Customer</T>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          <Chip label="Someone else" on={!uid} onPress={() => setUid("")} />
          {quotes.map((x) => <Chip key={x.user_id} label={x.job.name ?? x.user_id} on={uid === x.user_id} onPress={() => setUid(x.user_id)} />)}
        </View>
      </View>
      {!q && (<><Field label="Name" value={name} onChangeText={setName} /><Field label="Address" value={address} onChangeText={setAddress} /></>)}
      {q?.job.preferred_datetime ? <Banner kind="warn" text={`Customer asked for: ${q.job.preferred_datetime}`} /> : null}
      {sug.length > 0 && (
        <View style={{ gap: 6 }}>
          <T v="label">Suggested by Gesir</T>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
            {sug.slice(0, 4).map((s) => <Chip key={s.start} label={`${dayName(new Date(s.start))} ${clock(hhmm(new Date(s.start)))}`} onPress={() => use(s)} />)}
          </View>
        </View>
      )}
      <SlotPicker date={date} time={time} hours={hours} setDate={setDate} setTime={setTime} setHours={(h) => { setHours(h); setTouched(true); }} />
      <Guard conflicts={conflicts} onNext={next ? () => use(next) : undefined} />
      {err != null && <Banner text={explainError(err)} />}
      <Btn label={conflicts.length ? "Time is taken" : "Confirm booking"} busy={busy} disabled={conflicts.length > 0 || !customer.trim() || !date} onPress={save} />
    </Sheet>
  );
}

function EditSheet({ b, onClose, onSaved }: { b: Booking | null; onClose: () => void; onSaved: () => void }) {
  const [date, setDate] = useState("");
  const [time, setTime] = useState("09:00");
  const [hours, setHours] = useState(2);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!b) return;
    const s = new Date(b.start);
    setDate(key(s));
    setTime(hhmm(s));
    setHours(Math.max(0.5, Math.round(hoursOf(b) * 2) / 2));
    setErr(null);
    setBusy(false);
  }, [b]);

  const conflicts = useConflicts(date || key(new Date()), time, hours, b?.id);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setErr(null);
    try { await fn(); onSaved(); } catch (e) { setErr(e); setBusy(false); }
  }

  const cancelled = b?.status === "cancelled";
  return (
    <Sheet visible={!!b} title={b?.customer ?? ""} onClose={onClose}>
      {b && (
        <>
          <Group>
            <Row title="Status" right={<View style={{ flexDirection: "row", gap: 6 }}><Pill status={b.status} /><Pill status={b.quote_status} /></View>} />
            {b.quote_total != null ? <Row title="Quote" value={money(b.quote_total)} chevron={false} /> : null}
            <Row title="Address" value={b.address} chevron={false} />
          </Group>
          {!cancelled && <SlotPicker date={date} time={time} hours={hours} setDate={setDate} setTime={setTime} setHours={setHours} />}
          {!cancelled && <Guard conflicts={conflicts} />}
          {err != null && <Banner text={explainError(err)} />}
          {cancelled ? (
            <Btn kind="danger" label="Remove from calendar" busy={busy} onPress={() => run(() => api.deleteBooking(b.id))} />
          ) : (
            <>
              <Btn label={conflicts.length ? "Time is taken" : "Save changes"} busy={busy} disabled={conflicts.length > 0} onPress={() => { const s = at(date, time); run(() => api.updateBooking(b.id, { start: s.toISOString(), end: new Date(s.getTime() + hours * 3_600_000).toISOString() })); }} />
              <Btn kind="tinted" icon="calendar-outline" label="Add to Google Calendar" onPress={() => Linking.openURL(googleCalendarUrl({ title: `${b.customer} (Gesir)`, start: b.start, end: b.end, location: b.address, details: b.phone ? `WhatsApp: +${b.phone}` : "" }))} />
              <Btn kind="danger" label="Cancel booking" disabled={busy} onPress={() => run(() => api.updateBooking(b.id, { status: "cancelled" }))} />
            </>
          )}
        </>
      )}
    </Sheet>
  );
}
