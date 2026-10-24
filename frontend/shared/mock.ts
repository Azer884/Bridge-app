import { EXTRA_QUOTES, appendAudit, getDetail, store as detailStore, stubPdf, stubRecalc, stubSlots } from "./mock-detail";
import { fallbackStage } from "./params";
import type { AuditEntry, Interval, ParamValue, PdfPreview, PipelineRow, QuoteDetail, Recalculation, Slot, Stage } from "./types";
import type {
  AppEvent,
  Booking,
  BookingInput,
  ModelHealth,
  PersonasResponse,
  QuoteItem,
  QuoteStatus,
  WhatsAppLink,
} from "./types";

const wait = (ms = 350) => new Promise((r) => setTimeout(r, ms));
const now = Date.now();
const ago = (min: number) => new Date(now - min * 60_000).toISOString();

export class MockError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

const lines = (rows: [string, number, string, number, string][]) =>
  rows.map(([description, quantity, unit, unit_price, category]) => ({
    description,
    quantity,
    unit,
    unit_price,
    amount: Math.round(quantity * unit_price * 100) / 100,
    category,
  }));

let quotes: QuoteItem[] = [
  {
    user_id: "60123456789",
    status: "pending_approval",
    customer: "whatsapp",
    updated_at: ago(6),
    job: {
      name: "Nurul Aina",
      phone: "60123456789",
      address: "12, Jalan SS 15/4, Subang Jaya, Selangor",
      surfaces: "Leaking kitchen sink and worn mixer tap",
      surface_condition: "Dripping under the sink since yesterday, cabinet floor is wet",
      preferred_datetime: "Saturday morning, maybe 9am",
    },
    quote: {
      status: "draft_ready",
      currency: "MYR",
      total: 380,
      breakdown: {
        Labour: 140,
        "Parts & materials": 118,
        "Call-out": 60,
        "Overheads & profit": 62,
      },
      lines: lines([
        ["Call-out and diagnosis", 1, "visit", 60, "Call-out"],
        ["Replace waste trap and reseal joints", 2, "h", 70, "Labour"],
        ["Mixer tap, chrome", 1, "pc", 88, "Parts & materials"],
        ["Fittings, PTFE tape, sealant", 1, "set", 30, "Parts & materials"],
        ["Overheads and margin", 1, "lot", 62, "Overheads & profit"],
      ]),
      flags: ["Possible damp in the cabinet base. Check on site."],
      assumptions: ["Isolation valves still work", "Standard 40 mm waste pipe"],
      minimum_charge_applied: false,
    },
  },
  {
    user_id: "60198765432",
    status: "pending_approval",
    customer: "whatsapp",
    updated_at: ago(41),
    job: {
      name: "Daniel Lim",
      phone: "60198765432",
      address: "Unit 8-3, Residensi Bayu, Cheras, Kuala Lumpur",
      surfaces: "Master bedroom, 3 walls",
      room_length_m: 3.6,
      room_width_m: 3.2,
      room_height_m: 2.6,
      surface_condition: "Good, last painted two years ago",
      preferred_datetime: "Next week, any weekday evening",
    },
    quote: {
      status: "draft_ready",
      currency: "MYR",
      total: 480,
      breakdown: {
        Labour: 260,
        Paint: 96,
        "Surface preparation": 30,
        "Materials & sundries": 34,
        "Overheads & profit": 60,
      },
      lines: lines([
        ["Wall repaint, 2 coats emulsion", 26.5, "m²", 8.5, "Labour"],
        ["Emulsion paint", 5, "L", 19.2, "Paint"],
        ["Light sanding", 1, "job", 30, "Surface preparation"],
        ["Masking and sheets", 1, "set", 34, "Materials & sundries"],
        ["Overheads and margin", 1, "lot", 60, "Overheads & profit"],
      ]),
      flags: [],
      assumptions: ["Minimum charge covers one small room"],
      minimum_charge_applied: true,
    },
  },
  {
    user_id: "60172223344",
    status: "pending_approval",
    customer: "whatsapp",
    updated_at: ago(190),
    job: {
      name: "Tan Mei Ling",
      phone: "60172223344",
      address: "No. 3, Lorong Maarof, Bangsar, Kuala Lumpur",
      surfaces: "Kitchen cabinet install and four new power points",
      surface_condition: "Old cabinets removed, walls are bare brick",
      preferred_datetime: "Anytime in November",
    },
    quote: {
      status: "draft_ready",
      currency: "MYR",
      total: 4650,
      breakdown: {
        Labour: 1800,
        "Parts & materials": 1900,
        "Call-out": 150,
        "Overheads & profit": 800,
      },
      lines: lines([
        ["Install base and wall cabinets", 3, "day", 450, "Labour"],
        ["Run four new power points", 1, "job", 450, "Labour"],
        ["Cabinet set, laminate finish", 1, "set", 1500, "Parts & materials"],
        ["Cables, conduit, sockets", 1, "set", 400, "Parts & materials"],
        ["Site survey", 1, "visit", 150, "Call-out"],
        ["Overheads and margin", 1, "lot", 800, "Overheads & profit"],
      ]),
      flags: ["Electrical work may need a licensed electrician sign-off.", "Cabinet lead time is about 3 weeks."],
      assumptions: ["Walls are brick, not drywall", "Existing DB board has spare ways"],
      minimum_charge_applied: false,
    },
  },
  {
    user_id: "60134445566",
    status: "needs_inspection",
    customer: "whatsapp",
    updated_at: ago(75),
    job: {
      name: "Hafiz Rahman",
      phone: "60134445566",
      address: "Lot 22, Taman Melawati, Kuala Lumpur",
      surfaces: "Bathroom ceiling and wall",
      surface_condition: "Black mould and water stains, possible leak",
      preferred_datetime: "As soon as possible",
    },
    quote: null,
  },
  {
    user_id: "60187778899",
    status: "approved",
    customer: "whatsapp",
    updated_at: ago(60 * 26),
    job: {
      name: "Siti Zulaikha",
      phone: "60187778899",
      address: "A-12-5, Pavilion Residences, Bukit Jalil",
      surfaces: "Whole apartment, feature wall in grey",
      room_length_m: 9,
      room_width_m: 7,
      room_height_m: 2.7,
      surface_condition: "New unit, bare walls",
      preferred_datetime: "Friday 14 Nov, afternoon",
    },
    quote: {
      status: "approved",
      currency: "MYR",
      total: 3920,
      breakdown: {
        Labour: 1640,
        Paint: 1020,
        "Surface preparation": 420,
        "Materials & sundries": 240,
        "Overheads & profit": 600,
      },
      lines: lines([
        ["Walls, 2 coats emulsion over sealer", 146, "m²", 11.2, "Labour"],
        ["Emulsion and sealer", 52, "L", 19.6, "Paint"],
        ["Skim coat patches", 1, "job", 420, "Surface preparation"],
        ["Masking and sundries", 1, "set", 240, "Materials & sundries"],
        ["Overheads and margin", 1, "lot", 600, "Overheads & profit"],
      ]),
      flags: [],
      assumptions: ["Unit is empty during works"],
      minimum_charge_applied: false,
    },
  },
];

quotes.push(...EXTRA_QUOTES);

function stageFor(q: QuoteItem): Stage {
  if (q.status === "approved") {
    const upcoming = bookings.some((b) => b.user_id === q.user_id && b.status !== "cancelled" && new Date(b.end).getTime() > Date.now());
    return upcoming ? "scheduled" : "quote_sent";
  }
  return fallbackStage(q.status);
}

let personas: PersonasResponse = {
  active: "aisha",
  personas: {
    aisha: {
      name: "Aisha",
      style: "Warm and quick. Short sentences, a little Malaysian English, one emoji at most.",
      greeting: "Hi, this is {name} from {business}. Tell me about the job and I will get you a price.",
      service_question: "What do you need done?",
      closing: "Thank you. {owner} will check the price and I will send it here shortly.",
    },
    ben: {
      name: "Ben",
      style: "Calm and precise. Plain words, no slang, never more than two sentences at a time.",
      greeting: "Good day, I am {name} at {business}. I will ask a few questions about the job.",
      service_question: "What can we help you with?",
      closing: "Noted. {owner} is reviewing your quote and will confirm the final price.",
    },
    kak_lin: {
      name: "Kak Lin",
      style: "Friendly neighbour who knows the trade. Casual, reassuring, explains terms if the customer seems unsure.",
      greeting: "Hello! {name} here from {business}. Don't worry, I will guide you step by step.",
      service_question: "What needs fixing or building?",
      closing: "Alright, done on my side. {owner} will send your price soon.",
    },
  },
};

const startedAt = Date.now();
const WAKE_MS = 15_000;

let failedOnce = false;

const events: AppEvent[] = [
  { ts: ago(2), kind: "webhook.whatsapp", ok: true, detail: "Message from 60123456789: Saturday morning is fine" },
  { ts: ago(6), kind: "quote.draft", ok: true, detail: "Draft ready for 60123456789, total 380.00 MYR" },
  { ts: ago(41), kind: "quote.draft", ok: true, detail: "Draft ready for 60198765432, minimum charge applied" },
  { ts: ago(75), kind: "quote.inspection", ok: true, detail: "60134445566 needs inspection: possible leak" },
  { ts: ago(120), kind: "send.whatsapp", ok: false, detail: "502 from WhatsApp: outside the 24 hour window" },
  { ts: ago(60 * 26), kind: "send.whatsapp", ok: true, detail: "Total MYR 3,920.00 sent to 60187778899" },
];

function at(dayOffset: number, hour: number, minutes = 0, hours = 2): { start: string; end: string } {
  const s = new Date();
  s.setHours(hour, minutes, 0, 0);
  s.setDate(s.getDate() + dayOffset);
  const e = new Date(s.getTime() + hours * 3_600_000);
  return { start: s.toISOString(), end: e.toISOString() };
}

let bookings: Booking[] = [
  {
    id: "bk_1",
    user_id: "60187778899",
    customer: "Siti Zulaikha",
    phone: "60187778899",
    address: "A-12-5, Pavilion Residences, Bukit Jalil",
    ...at(1, 14, 0, 6),
    status: "confirmed",
    quote_status: "approved",
    quote_total: 3920,
  },
  {
    id: "bk_2",
    user_id: "60123456789",
    customer: "Nurul Aina",
    phone: "60123456789",
    address: "12, Jalan SS 15/4, Subang Jaya",
    ...at(3, 9, 0, 4),
    status: "tentative",
    quote_status: "pending_approval",
    quote_total: 380,
  },
  {
    id: "bk_3",
    user_id: "60134445566",
    customer: "Hafiz Rahman",
    phone: "60134445566",
    address: "Lot 22, Taman Melawati",
    ...at(0, 16, 0, 1),
    status: "confirmed",
    quote_status: "needs_inspection",
    quote_total: null,
  },
  {
    id: "bk_4",
    user_id: "60198765432",
    customer: "Daniel Lim",
    phone: "60198765432",
    address: "Unit 8-3, Residensi Bayu, Cheras",
    ...at(6, 19, 0, 3),
    status: "tentative",
    quote_status: "pending_approval",
    quote_total: 480,
  },
];

let wa: WhatsAppLink = { number: null, status: "unlinked" };
let waLinkedAt = 0;

export const mockApi = {
  async whatsappStatus(): Promise<WhatsAppLink> {
    await wait(200);
    if (wa.status === "pending" && Date.now() - waLinkedAt > 4000) wa = { ...wa, status: "linked" };
    return { ...wa };
  },

  async linkWhatsapp(number: string): Promise<WhatsAppLink> {
    await wait(500);
    const digits = number.replace(/\D/g, "");
    if (digits.length < 9) throw new MockError(422, "Enter the full number with country code");
    wa = { number: digits, status: "pending" };
    waLinkedAt = Date.now();
    return { ...wa };
  },

  async unlinkWhatsapp(): Promise<void> {
    await wait(300);
    wa = { number: null, status: "unlinked" };
  },

  async getQuoteDetail(userId: string): Promise<QuoteDetail> {
    await wait(300);
    const q = quotes.find((x) => x.user_id === userId);
    if (!q) throw new MockError(404, "Quote not found");
    return getDetail(q, bookings, stageFor(q));
  },

  async recalculate(userId: string, params: Record<string, ParamValue>): Promise<Recalculation> {
    await wait(350 + Math.random() * 300);
    const q = quotes.find((x) => x.user_id === userId);
    if (!q?.quote || !detailStore[userId]?.params) throw new MockError(409, "Nothing to calculate yet");
    return stubRecalc(q, params);
  },

  async saveParams(userId: string, params: Record<string, ParamValue>): Promise<void> {
    await wait(300);
    const q = quotes.find((x) => x.user_id === userId);
    const s = detailStore[userId];
    if (!q?.quote || !s?.params) throw new MockError(409, "Nothing to save yet");
    if (s.locked) throw new MockError(409, "This quote was already sent");
    const changes = s.params.schema
      .filter((f) => s.params!.current[f.key] !== params[f.key])
      .map((f) => ({ field: f.label, from: String(s.params!.current[f.key] ?? "-"), to: String(params[f.key]) }));
    if (!changes.length) return;
    s.params.current = { ...params };
    const calc = stubRecalc(q, params);
    q.quote = calc.quote;
    s.duration = calc.duration_hours;
    appendAudit(userId, "owner", "override", `Overrode ${changes.length} value${changes.length === 1 ? "" : "s"}`, changes);
    appendAudit(userId, "system", "calculation", `Price recalculated: ${(calc.quote.total ?? 0).toFixed(2)} MYR`);
  },

  async pdfPreview(userId: string, params: Record<string, ParamValue>): Promise<PdfPreview> {
    await wait(600);
    const q = quotes.find((x) => x.user_id === userId);
    if (!q?.quote) throw new MockError(409, "No quote to preview yet");
    const quote = detailStore[userId]?.params ? stubRecalc(q, params).quote : q.quote;
    appendAudit(userId, "owner", "pdf", "Previewed quote PDF");
    return stubPdf(q, quote);
  },

  async listPipeline(): Promise<PipelineRow[]> {
    await wait(300);
    return JSON.parse(JSON.stringify(quotes.map((q) => ({ ...q, stage: stageFor(q) }))));
  },

  async listActivity(limit = 20): Promise<(AuditEntry & { user_id: string; customer: string })[]> {
    await wait(250);
    return Object.entries(detailStore)
      .flatMap(([uid, s]) => s.audit.map((a) => ({ ...a, user_id: uid, customer: quotes.find((q) => q.user_id === uid)?.job.name ?? uid })))
      .sort((a, b) => b.ts.localeCompare(a.ts))
      .slice(0, limit);
  },

  async suggestSlots(userId: string, busy: Interval[] = []): Promise<Slot[]> {
    await wait(500);
    const hours = detailStore[userId]?.duration ?? 2;
    return stubSlots(hours, bookings, busy, userId);
  },

  async listQuotes(status?: QuoteStatus): Promise<QuoteItem[]> {
    await wait();
    const list = status ? quotes.filter((q) => q.status === status) : quotes;
    return JSON.parse(JSON.stringify(list));
  },

  async approveQuote(userId: string, total?: number): Promise<{ ok: true; total: number }> {
    await wait(700);
    const q = quotes.find((x) => x.user_id === userId);
    if (!q || q.status !== "pending_approval" || !q.quote) throw new MockError(409, "Nothing pending for this customer");
    if (total != null && !(total > 0)) throw new MockError(422, "Total must be above zero");
    if (userId === "60172223344" && !failedOnce) {
      failedOnce = true;
      throw new MockError(502, "WhatsApp send failed");
    }
    const final = total ?? q.quote.total ?? 0;
    if (total != null && Math.abs(total - (q.quote.total ?? 0)) > 0.004) {
      appendAudit(userId, "owner", "override", "Adjusted final total", [{ field: "Total", from: (q.quote.total ?? 0).toFixed(2), to: total.toFixed(2) }]);
    }
    q.status = "approved";
    if (detailStore[userId]) detailStore[userId].locked = true;
    q.quote.status = "approved";
    q.quote.total = final;
    q.updated_at = new Date().toISOString();
    appendAudit(userId, "owner", "send", `Approved and sent ${final.toFixed(2)} MYR to customer`);
    appendAudit(userId, "system", "state_change", "Moved to Quote sent");
    events.unshift({
      ts: q.updated_at,
      kind: "send.whatsapp",
      ok: true,
      detail: `Total MYR ${final.toFixed(2)} sent to ${userId}`,
    });
    return { ok: true, total: final };
  },

  async listPersonas(): Promise<PersonasResponse> {
    await wait(250);
    return JSON.parse(JSON.stringify(personas));
  },

  async savePersona(id: string, body: PersonasResponse["personas"][string]): Promise<void> {
    await wait(300);
    personas.personas[id] = { ...body };
  },

  async setActivePersona(id: string): Promise<void> {
    await wait(250);
    if (!personas.personas[id]) throw new MockError(404, "Unknown persona");
    personas.active = id;
  },

  async listEvents(limit = 50): Promise<AppEvent[]> {
    await wait(250);
    return events.slice(0, limit);
  },

  async modelHealth(): Promise<ModelHealth> {
    await wait(200);
    if (Date.now() - startedAt < WAKE_MS) {
      return { state: "waking", label: "Waking up", detail: "Worker is cold. This takes 2 to 5 minutes." };
    }
    return { state: "ready", label: "Ready", detail: "1 worker idle, last reply 2.4 s" };
  },

  async listBookings(from: string, to: string): Promise<Booking[]> {
    await wait(200);
    const f = new Date(from).getTime();
    const t = new Date(to).getTime();
    return bookings.filter((b) => {
      const s = new Date(b.start).getTime();
      return s >= f && s < t;
    });
  },

  async createBooking(input: BookingInput): Promise<Booking> {
    await wait(300);
    const clash = bookings.find(
      (b) =>
        b.status !== "cancelled" &&
        new Date(input.start) < new Date(b.end) &&
        new Date(input.end) > new Date(b.start),
    );
    if (clash) throw new MockError(409, `Overlaps with ${clash.customer}`);
    const q = quotes.find((x) => x.user_id === input.user_id);
    const b: Booking = {
      id: `bk_${Math.random().toString(36).slice(2, 8)}`,
      ...input,
      status: "confirmed",
      quote_status: q?.status ?? "none",
      quote_total: q?.quote?.total ?? null,
    };
    bookings = [...bookings, b];
    appendAudit(input.user_id, "owner", "schedule", `Booked ${new Date(input.start).toLocaleString("en-MY", { weekday: "short", hour: "numeric", minute: "2-digit" })}`);
    return b;
  },

  async updateBooking(id: string, patch: Partial<Pick<Booking, "start" | "end" | "status">>): Promise<Booking> {
    await wait(250);
    const b = bookings.find((x) => x.id === id);
    if (!b) throw new MockError(404, "Booking not found");
    const next = { ...b, ...patch };
    if (patch.start || patch.end) {
      const clash = bookings.find(
        (o) =>
          o.id !== id &&
          o.status !== "cancelled" &&
          new Date(next.start) < new Date(o.end) &&
          new Date(next.end) > new Date(o.start),
      );
      if (clash) throw new MockError(409, `Overlaps with ${clash.customer}`);
    }
    Object.assign(b, next);
    return { ...b };
  },

  async deleteBooking(id: string): Promise<void> {
    await wait(250);
    bookings = bookings.filter((b) => b.id !== id);
  },
};






