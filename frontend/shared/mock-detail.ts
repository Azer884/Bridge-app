/**
 * Sample data for the new review features. Everything here stands in for the real backend:
 * recalculation, PDF, slot suggestions and the audit log all come from the API in live mode.
 */
import { findConflicts } from "./params";
import { SCHEMAS } from "./mock-schemas";
import type {
  AuditActor, AuditEntry, AuditType, Booking, ChatMessage, ExtractedParams, Interval, ParamValue, PdfPreview,
  Photo, QuoteDetail, QuoteDraft, QuoteItem, Recalculation, Slot,
} from "./types";

const ago = (min: number) => new Date(Date.now() - min * 60_000).toISOString();

const svg = (inner: string, bg: string) =>
  `data:image/svg+xml;utf8,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 480"><rect width="640" height="480" fill="${bg}"/>${inner}</svg>`,
  )}`;

const SCENES: Record<string, string> = {
  leak: svg(`<rect x="60" y="260" width="520" height="200" fill="#b9a58c"/><rect x="60" y="260" width="520" height="14" fill="#8f7d66"/><ellipse cx="330" cy="420" rx="170" ry="26" fill="#5b4a3a" opacity=".55"/><rect x="300" y="80" width="40" height="190" fill="#9aa5ab"/><rect x="280" y="250" width="80" height="24" rx="6" fill="#7e898f"/><circle cx="320" cy="300" r="9" fill="#3b82a0"/><circle cx="324" cy="340" r="7" fill="#3b82a0"/>`, "#d9d4cc"),
  tap: svg(`<rect x="0" y="330" width="640" height="150" fill="#a9b3b8"/><path d="M250 330V190q0-60 70-60h60v40h-50q-30 0-30 30v130z" fill="#c9d2d6" stroke="#7e898f" stroke-width="6"/><circle cx="388" cy="230" r="8" fill="#3b82a0"/>`, "#e6e9ea"),
  crack: svg(`<rect x="70" y="60" width="200" height="260" fill="#cfe3ea" stroke="#8aa3ad" stroke-width="8"/><path d="M360 40l30 90-40 70 50 80-20 70 30 90" fill="none" stroke="#5c5a55" stroke-width="5"/>`, "#e9e2d3"),
  room: svg(`<rect x="0" y="360" width="640" height="120" fill="#b89f84"/><rect x="420" y="70" width="170" height="220" fill="#cfe3ea" stroke="#8aa3ad" stroke-width="8"/><rect x="60" y="250" width="240" height="110" rx="10" fill="#7d8f9b"/>`, "#efe9dd"),
  kitchen: svg(`<rect x="40" y="250" width="560" height="180" fill="#8a6f55"/><rect x="40" y="230" width="560" height="26" fill="#d8d2c8"/><rect x="40" y="60" width="240" height="130" fill="#a28668"/><rect x="360" y="60" width="240" height="130" fill="#a28668"/><path d="M0 460h640" stroke="#6b5a49" stroke-width="12"/>`, "#e8e4dc"),
  mould: svg(`<path d="M0 0h640v110L0 190z" fill="#d7d3cb"/><g fill="#2f3b2c" opacity=".7"><circle cx="90" cy="140" r="30"/><circle cx="150" cy="160" r="22"/><circle cx="60" cy="190" r="18"/><circle cx="210" cy="200" r="14"/><circle cx="300" cy="170" r="10"/></g><rect x="360" y="260" width="220" height="150" fill="#a9b3b8"/>`, "#e3dfd6"),
  shop: svg(`<rect x="60" y="80" width="520" height="300" fill="#b9c3c9"/><rect x="100" y="230" width="150" height="150" fill="#6f7e88"/><rect x="300" y="130" width="230" height="130" fill="#cfe3ea" stroke="#8aa3ad" stroke-width="8"/>`, "#e6e6e1"),
};

const photo = (id: string, scene: keyof typeof SCENES, caption: string, min: number): Photo => ({
  id, url: SCENES[scene], caption, ts: ago(min),
});

const msg = (id: string, role: ChatMessage["role"], text: string, min: number, photo_ids?: string[]): ChatMessage => ({
  id, role, text, ts: ago(min), photo_ids,
});

const fnv = (s: string) => {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, "0");
};

type Row = [AuditActor, AuditType, string, number, AuditEntry["changes"]?];
function chain(rows: Row[]): AuditEntry[] {
  let prev = "genesis";
  return rows.map(([actor, type, summary, min, changes], i) => {
    const hash = fnv(prev + summary + min);
    prev = hash;
    return { seq: i + 1, ts: ago(min), actor, type, summary, changes, hash };
  });
}

const P = (kind: ExtractedParams["kind"], ai: Record<string, ParamValue>, confidence: Record<string, number>): ExtractedParams => ({
  kind, schema: SCHEMAS[kind], ai: { ...ai }, current: { ...ai }, confidence,
});

interface Seed {
  params: ExtractedParams | null;
  chat: ChatMessage[];
  photos: Photo[];
  audit: AuditEntry[];
  duration: number | null;
  locked: boolean;
}

const seeds: Record<string, Seed> = {
  "60123456789": {
    params: P("plumbing", { labour_hours: 2, parts_cost: 118, urgency: "standard" }, { labour_hours: 0.62, parts_cost: 0.9, urgency: 0.95 }),
    photos: [photo("p1", "leak", "Water under the sink", 52), photo("p2", "tap", "Old mixer tap", 51)],
    chat: [
      msg("m1", "customer", "Hi, my kitchen sink is leaking.", 58),
      msg("m2", "assistant", "Sorry to hear that. Is it dripping or running?", 58),
      msg("m3", "customer", "Dripping under the sink since yesterday. Cabinet floor is wet.", 56, ["p1"]),
      msg("m4", "assistant", "Thanks. Could you send a photo of the tap too?", 55),
      msg("m5", "customer", "Here. It is quite old.", 51, ["p2"]),
      msg("m6", "assistant", "Got it. Which area are you in, and when suits you?", 50),
      msg("m7", "customer", "Subang Jaya. Saturday morning, maybe 9am.", 48),
      msg("m8", "assistant", "Thank you. The owner will check the price and I will send it here shortly.", 47),
    ],
    audit: chain([
      ["customer", "state_change", "Customer started a chat on WhatsApp", 58],
      ["ai", "ai_extraction", "Extracted job details from chat and 2 photos", 47, [
        { field: "Labour", from: "-", to: "2 h" }, { field: "Parts and fittings", from: "-", to: "118 MYR" }, { field: "Urgency", from: "-", to: "Standard" },
      ]],
      ["system", "calculation", "Draft price calculated: 380.00 MYR", 46],
      ["system", "state_change", "Moved to Needs your approval", 46],
    ]),
    duration: 2.5, locked: false,
  },
  "60198765432": {
    params: P("painting", { length_m: 3.6, width_m: 3.2, height_m: 2.6, surface_condition: "good", coats: 2, tier: "standard" }, { length_m: 0.93, width_m: 0.93, height_m: 0.8, surface_condition: 0.88, coats: 0.97, tier: 0.7 }),
    photos: [photo("p1", "room", "Master bedroom", 120)],
    chat: [
      msg("m1", "customer", "Need to repaint my master bedroom.", 130),
      msg("m2", "assistant", "Happy to help. About how big is the room?", 130),
      msg("m3", "customer", "3.6 by 3.2, ceiling 2.6 I think.", 128),
      msg("m4", "assistant", "Thanks. Can you send a photo, and tell me when it was last painted?", 127),
      msg("m5", "customer", "Two years ago, still good.", 124, ["p1"]),
      msg("m6", "assistant", "Perfect. Any preference on paint quality?", 123),
      msg("m7", "customer", "Normal is fine.", 121),
    ],
    audit: chain([
      ["customer", "state_change", "Customer started a chat on WhatsApp", 130],
      ["ai", "ai_extraction", "Extracted room size, condition, coats and paint tier", 120],
      ["system", "calculation", "Draft price calculated: 480.00 MYR (minimum charge)", 119],
      ["system", "state_change", "Moved to Needs your approval", 119],
    ]),
    duration: 4, locked: false,
  },
  "60172223344": {
    params: P("general", { crew_days: 3, materials_cost: 1900, specialist_cost: 450 }, { crew_days: 0.6, materials_cost: 0.82, specialist_cost: 0.55 }),
    photos: [photo("p1", "kitchen", "Kitchen, cabinets removed", 300), photo("p2", "crack", "Wall where sockets go", 299)],
    chat: [
      msg("m1", "customer", "I need new kitchen cabinets installed and four power points.", 310),
      msg("m2", "assistant", "Sure. Are the old cabinets already removed?", 310),
      msg("m3", "customer", "Yes. Walls are bare brick.", 305, ["p1", "p2"]),
      msg("m4", "assistant", "Thanks. Which month suits you?", 304),
      msg("m5", "customer", "Anytime in November.", 301),
    ],
    audit: chain([
      ["customer", "state_change", "Customer started a chat on WhatsApp", 310],
      ["ai", "ai_extraction", "Extracted crew days and materials from chat and 2 photos", 298],
      ["system", "calculation", "Draft price calculated: 4,650.00 MYR", 297],
      ["system", "state_change", "Moved to Needs your approval", 297],
    ]),
    duration: 12, locked: false,
  },
  "60134445566": {
    params: null,
    photos: [photo("p1", "mould", "Black mould on ceiling", 90), photo("p2", "leak", "Wet patch on wall", 89)],
    chat: [
      msg("m1", "customer", "Bathroom ceiling has black mould and water stains.", 100),
      msg("m2", "assistant", "That sounds like it needs a look. Can you send photos?", 100),
      msg("m3", "customer", "Here.", 90, ["p1", "p2"]),
      msg("m4", "assistant", "Thank you. Possible leak, so the owner will arrange a visit before pricing.", 89),
    ],
    audit: chain([
      ["customer", "state_change", "Customer started a chat on WhatsApp", 100],
      ["ai", "ai_extraction", "Could not price from chat: possible leak behind wall", 89],
      ["system", "state_change", "Moved to Needs your approval, inspection needed", 89],
    ]),
    duration: 1, locked: false,
  },
  "60187778899": {
    params: P("painting", { length_m: 9, width_m: 7, height_m: 2.7, surface_condition: "good", coats: 2, tier: "premium" }, { length_m: 0.95, width_m: 0.95, height_m: 0.9, surface_condition: 0.9, coats: 0.95, tier: 0.9 }),
    photos: [photo("p1", "room", "Living area", 1700)],
    chat: [
      msg("m1", "customer", "New apartment, need the whole unit painted. One feature wall in grey.", 1800),
      msg("m2", "assistant", "Congratulations! Roughly how big is the unit?", 1800),
      msg("m3", "customer", "About 9 by 7 metres, bare walls.", 1750, ["p1"]),
      msg("m4", "assistant", "Thanks, the owner will confirm the price shortly.", 1749),
      msg("m5", "owner", "Total MYR 3,920.00 for the whole unit, two coats premium paint.", 1560),
      msg("m6", "customer", "Great, Friday afternoon please.", 1500),
    ],
    audit: chain([
      ["customer", "state_change", "Customer started a chat on WhatsApp", 1800],
      ["ai", "ai_extraction", "Extracted room size, condition, coats and paint tier", 1745],
      ["system", "calculation", "Draft price calculated: 3,920.00 MYR", 1744],
      ["owner", "pdf", "Previewed quote PDF", 1565],
      ["owner", "send", "Approved and sent 3,920.00 MYR to customer", 1560],
      ["system", "schedule", "Booked Friday 14:00 to 20:00", 1480],
      ["system", "state_change", "Moved to Scheduled and booked", 1480],
    ]),
    duration: 6, locked: true,
  },
  "60165554433": {
    params: P("painting", { length_m: 4, width_m: null, height_m: null, surface_condition: null, coats: null, tier: null }, { length_m: 0.7 }),
    photos: [],
    chat: [
      msg("m1", "customer", "Hi, I want to repaint my living room.", 4),
      msg("m2", "assistant", "Happy to help. About how big is the room?", 4),
      msg("m3", "customer", "Length is around 4 metres.", 2),
      msg("m4", "assistant", "Thanks. And the width?", 2),
    ],
    audit: chain([
      ["customer", "state_change", "Customer started a chat on WhatsApp", 4],
      ["ai", "ai_extraction", "Extracted room length so far", 2, [{ field: "Room length", from: "-", to: "4 m" }]],
    ]),
    duration: null, locked: false,
  },
  "60143332211": {
    params: P("painting", { length_m: 8, width_m: 5, height_m: 3, surface_condition: "fair", coats: 2, tier: "standard" }, { length_m: 0.9, width_m: 0.9, height_m: 0.9, surface_condition: 0.8, coats: 0.95, tier: 0.9 }),
    photos: [photo("p1", "shop", "Shop front wall", 9000)],
    chat: [
      msg("m1", "customer", "Shop interior needs repainting before we reopen.", 9100),
      msg("m2", "assistant", "Sure. How big is the space?", 9100),
      msg("m3", "customer", "8 by 5, ceiling 3.", 9090, ["p1"]),
      msg("m4", "owner", "Total MYR 2,640.00. We can start Monday.", 8900),
      msg("m5", "customer", "Done, thank you!", 5000),
    ],
    audit: chain([
      ["customer", "state_change", "Customer started a chat on WhatsApp", 9100],
      ["ai", "ai_extraction", "Extracted room size, condition, coats and paint tier", 9085],
      ["owner", "override", "Changed Surface condition", 8920, [{ field: "Surface condition", from: "Good", to: "Fair, small repairs" }]],
      ["owner", "send", "Approved and sent 2,640.00 MYR to customer", 8900],
      ["system", "state_change", "Moved to Quote sent", 8900],
      ["owner", "state_change", "Marked job completed", 5000],
    ]),
    duration: 5, locked: true,
  },
};

export const EXTRA_QUOTES: QuoteItem[] = [
  { user_id: "60165554433", status: "collecting", customer: "whatsapp", updated_at: ago(2), job: { name: "Wong Kah Wai", phone: "60165554433", address: "Taman Desa, Kuala Lumpur", surfaces: "Living room" }, quote: null },
  {
    user_id: "60143332211", status: "completed", customer: "whatsapp", updated_at: ago(5000),
    job: { name: "Lee Chong Wei", phone: "60143332211", address: "Shop 12, Jalan Pudu, Kuala Lumpur", surfaces: "Shop interior", surface_condition: "Small repairs needed" },
    quote: {
      status: "approved", currency: "MYR", total: 2640, labor_hours: 20,
      breakdown: { Labour: 1100, Paint: 640, "Surface preparation": 260, "Materials & sundries": 160, "Overheads & profit": 480 },
      lines: [
        { description: "Repaint walls and ceiling, 2 coats", quantity: 20, unit: "h", unit_price: 55, amount: 1100, category: "Labour" },
        { description: "Standard emulsion", quantity: 32, unit: "L", unit_price: 20, amount: 640, category: "Paint" },
        { description: "Surface preparation", quantity: 1, unit: "job", unit_price: 260, amount: 260, category: "Surface preparation" },
        { description: "Masking and sundries", quantity: 1, unit: "set", unit_price: 160, amount: 160, category: "Materials & sundries" },
        { description: "Overheads and margin", quantity: 1, unit: "lot", unit_price: 480, amount: 480, category: "Overheads & profit" },
      ],
      flags: [], assumptions: [], minimum_charge_applied: false,
    },
  },
];

/** Details live here, keyed by user id, and change as the owner edits. */
export const store = seeds;

export function appendAudit(userId: string, actor: AuditActor, type: AuditType, summary: string, changes?: AuditEntry["changes"]) {
  const s = store[userId];
  if (!s) return;
  const prev = s.audit[s.audit.length - 1];
  s.audit.push({ seq: (prev?.seq ?? 0) + 1, ts: new Date().toISOString(), actor, type, summary, changes, hash: fnv((prev?.hash ?? "genesis") + summary + Date.now()) });
}

export function getDetail(item: QuoteItem, bookings: Booking[], stage: QuoteDetail["stage"]): QuoteDetail {
  const s = store[item.user_id];
  const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v));
  return {
    ...clone(item), stage,
    params: s ? clone(s.params) : null,
    chat: s ? clone(s.chat) : [],
    photos: s ? clone(s.photos) : [],
    audit: s ? clone(s.audit) : [],
    duration_hours: s?.duration ?? null,
    locked: s?.locked ?? false,
  };
}

const num = (v: ParamValue | undefined) => (typeof v === "number" && v > 0 ? v : null);
const ratio = (a: ParamValue | undefined, b: ParamValue | undefined) => {
  const x = num(a), y = num(b);
  return x && y ? x / y : 1;
};

/** Stand-in for the backend calculation engine: scales the draft by how far the inputs moved. */
export function stubRecalc(item: QuoteItem, params: Record<string, ParamValue>): Recalculation {
  const s = store[item.user_id];
  const base = item.quote as QuoteDraft;
  const ai = s.params!.ai;
  const scale = ["length_m", "width_m", "height_m", "coats", "labour_hours", "crew_days"].reduce((f, k) => f * ratio(params[k], ai[k]), 1);
  const tier = (v: ParamValue | undefined) => ({ economy: 0.72, standard: 1, premium: 1.45 })[String(v)] ?? 1;
  const cond = (v: ParamValue | undefined) => ({ good: 1, fair: 3, poor: 7 })[String(v)] ?? 1;
  const partsR = ratio(params.parts_cost, ai.parts_cost) * ratio(params.materials_cost, ai.materials_cost);
  const factor: Record<string, number> = {
    Labour: scale * (params.urgency === "same_day" ? 1.25 : 1) / (ai.urgency === "same_day" ? 1.25 : 1),
    Paint: scale * (tier(params.tier) / tier(ai.tier)),
    "Surface preparation": cond(params.surface_condition) / cond(ai.surface_condition),
    "Parts & materials": partsR === 1 ? 1 : partsR,
    "Materials & sundries": scale,
    "Call-out": 1,
  };
  const r2 = (n: number) => Math.round(n * 100) / 100;
  const lines = base.lines.map((l) => {
    const f = factor[l.category] ?? 1;
    return { ...l, amount: r2(l.amount * f), quantity: l.category === "Labour" || l.category === "Paint" ? r2(l.quantity * f) : l.quantity };
  });
  const breakdown: Record<string, number> = {};
  for (const l of lines) if (l.category !== "Overheads & profit") breakdown[l.category] = r2((breakdown[l.category] ?? 0) + l.amount);
  const sub = Object.values(breakdown).reduce((a, b) => a + b, 0);
  const baseSub = Object.entries(base.breakdown).filter(([k]) => k !== "Overheads & profit").reduce((a, [, v]) => a + v, 0);
  const over = r2(sub * ((base.breakdown["Overheads & profit"] ?? 0) / (baseSub || 1)));
  breakdown["Overheads & profit"] = over;
  const oi = lines.findIndex((l) => l.category === "Overheads & profit");
  if (oi >= 0) lines[oi] = { ...lines[oi], amount: over, unit_price: over };
  let total = r2(sub + over);
  if (base.minimum_charge_applied && total < (base.total ?? 0)) total = base.total ?? total;
  const hours = base.labor_hours != null ? r2(base.labor_hours * scale) : undefined;
  const flags = [...base.flags];
  if (params.surface_condition === "poor" && !flags.some((f) => f.includes("Poor surface"))) flags.push("Poor surface: confirm the extent of damage on site.");
  return {
    quote: { ...base, lines, breakdown, total, flags, labor_hours: hours },
    duration_hours: Math.min(40, Math.max(1, Math.round(((s.duration ?? 2) * scale) * 2) / 2)),
  };
}

/** Stand-in for the backend slot finder. Real one uses Google Calendar free/busy. */
export function stubSlots(durationHours: number, bookings: Booking[], busy: Interval[], userId = ""): Slot[] {
  const taken: (Interval & { id?: string })[] = [...bookings.filter((b) => b.status !== "cancelled"), ...busy];
  const out: Slot[] = [];
  const perDay: Record<string, number> = {};
  for (let d = 0; d < 14 && out.length < 5; d++) {
    const day = new Date();
    day.setDate(day.getDate() + d);
    if (day.getDay() === 0) continue;
    const sameDay = bookings.find((b) => b.user_id !== userId && b.status !== "cancelled" && new Date(b.start).toDateString() === day.toDateString());
    for (let h = 8; h + durationHours <= 18; h += 0.5) {
      const s = new Date(day);
      s.setHours(Math.floor(h), (h % 1) * 60, 0, 0);
      if (s.getTime() < Date.now() + 2 * 3_600_000) continue;
      const e = new Date(s.getTime() + durationHours * 3_600_000);
      const win = { start: s.toISOString(), end: e.toISOString() };
      if (findConflicts(win, taken).length) continue;
      const key = day.toDateString();
      if ((perDay[key] ?? 0) >= 1) break;
      perDay[key] = (perDay[key] ?? 0) + 1;
      out.push({
        ...win,
        score: Math.max(40, Math.round(98 - d * 4 - Math.abs(h - 9) * 2 + (sameDay ? 6 : 0))),
        reason: out.length === 0 ? "Earliest free window" : sameDay ? `Same day as ${sameDay.customer}, saves travel` : `Free for the full ${durationHours} h`,
      });
      break;
    }
  }
  return out;
}

/** Stand-in for the ReportLab PDF. Builds a one-page PDF so the viewer has something real to show. */
export function stubPdf(item: QuoteItem, quote: QuoteDraft): PdfPreview {
  const esc = (t: string) => t.replace(/[^\x20-\x7e]/g, "").replace(/([()\\])/g, "\\$1");
  const rows = [
    `Quote for ${item.job.name ?? item.user_id}`,
    item.job.address ?? "",
    "",
    ...quote.lines.map((l) => `${l.description}   ${l.quantity} ${l.unit.replace("²", "2")}   ${l.amount.toFixed(2)}`),
    "",
    `Total ${quote.currency} ${(quote.total ?? 0).toFixed(2)}`,
  ];
  const stream = ["BT /F1 18 Tf 56 780 Td (" + esc("Quote") + ") Tj ET"]
    .concat(rows.map((r, i) => `BT /F1 11 Tf 56 ${740 - i * 18} Td (${esc(r)}) Tj ET`))
    .join("\n");
  const objs = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  let pdf = "%PDF-1.4\n";
  const offs: number[] = [];
  objs.forEach((o, i) => {
    offs.push(pdf.length);
    pdf += `${i + 1} 0 obj\n${o}\nendobj\n`;
  });
  const xref = pdf.length;
  pdf += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n` + offs.map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("");
  pdf += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  return { base64: btoa(pdf), filename: `Quote-${item.user_id.slice(-4)}.pdf`, generated_at: new Date().toISOString() };
}

