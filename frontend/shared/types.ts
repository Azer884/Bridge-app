export type QuoteStatus = "pending_approval" | "approved" | "needs_inspection" | "collecting" | "completed" | "rejected";

/** Pipeline stage shown on the Pipeline page. Derived by the backend (or by stageOf in shared/calc.ts). */
export type Stage = "pending_extraction" | "requires_approval" | "quote_sent" | "scheduled" | "completed" | "rejected";

export interface Job {
  address?: string;
  surfaces?: string;
  room_length_m?: number;
  room_width_m?: number;
  room_height_m?: number;
  surface_condition?: string;
  preferred_datetime?: string;
  name?: string;
  phone?: string;
  /** A location the customer shared on WhatsApp; maps_url opens it in Google Maps. */
  location?: { lat: number; lon: number; name?: string; address?: string; maps_url: string } | null;
}

export interface QuoteLine {
  description: string;
  quantity: number;
  unit: string;
  unit_price: number;
  amount: number;
  category: string;
}

export interface QuoteDraft {
  status: string;
  currency: string;
  total: number | null;
  breakdown: Record<string, number>;
  lines: QuoteLine[];
  flags: string[];
  assumptions: string[];
  minimum_charge_applied: boolean;
  /** Set by the calculation engine. */
  labor_hours?: number;
  /** What the customer was sent as the estimate, and later as the final price after the visit. */
  approved_total?: number;
  final_total?: number;
}

export interface CustomerOrder {
  quote: QuoteDraft | null;
  quote_status?: string;
  created_at?: number;
  open?: boolean;
}

/** One customer with every job they have had, for order tracking. */
export interface Customer {
  user_id: string;
  name: string | null;
  phone: string | null;
  lang?: string;
  stage?: string;
  attention?: boolean;
  needs_human?: boolean;
  orders: CustomerOrder[];
}

export interface QuoteItem {
  user_id: string;
  status: QuoteStatus;
  customer: string;
  job: Job;
  quote: QuoteDraft | null;
  /** Not in the documented schema; shown when the backend sends it. */
  updated_at?: string;
  stage?: Stage;
  /** The assistant asked for a human, or the customer wrote something important while waiting. */
  needs_human?: boolean;
  attention?: boolean;
  /** The owner is replying by hand: the assistant is paused for this customer. */
  human_active?: boolean;
}

export type ParamValue = string | number | boolean | null;

export interface ParamField {
  key: string;
  label: string;
  type: "number" | "select";
  unit?: string;
  min?: number;
  max?: number;
  step?: number;
  integer?: boolean;
  options?: { value: string; label: string }[];
  help?: string;
}

export interface ExtractedParams {
  /** Which calculation engine and form layout apply. */
  kind: "painting" | "plumbing" | "general";
  schema: ParamField[];
  /** What the model extracted. Never changes. */
  ai: Record<string, ParamValue>;
  /** What the engine uses now: AI values plus owner overrides. */
  current: Record<string, ParamValue>;
  /** 0 to 1 per field. Under 0.7 is flagged for a check. */
  confidence: Record<string, number>;
}

export interface ChatMessage {
  id: string;
  role: "customer" | "assistant" | "owner";
  text: string;
  ts: string;
  photo_ids?: string[];
}

export interface Photo {
  id: string;
  url: string;
  caption: string;
  ts: string;
}

export type AuditActor = "customer" | "ai" | "system" | "owner";
export type AuditType = "state_change" | "ai_extraction" | "override" | "calculation" | "pdf" | "send" | "schedule";

export interface AuditEntry {
  /** Position in the log. Increases by one, never reused. */
  seq: number;
  ts: string;
  actor: AuditActor;
  type: AuditType;
  summary: string;
  changes?: { field: string; from: string; to: string }[];
  /** Short chain hash so tampering is visible. */
  hash: string;
}

export interface QuoteDetail extends QuoteItem {
  stage: Stage;
  params: ExtractedParams | null;
  chat: ChatMessage[];
  photos: Photo[];
  audit: AuditEntry[];
  /** Estimated time on site, from the calculation engine. */
  duration_hours: number | null;
  /** True once approved and sent: fields lock. */
  locked: boolean;
}

export interface Recalculation {
  quote: QuoteDraft;
  duration_hours: number;
}

export interface PdfPreview {
  /** Signed URL from the backend. */
  url?: string;
  /** Mock mode only. */
  base64?: string;
  filename: string;
  generated_at: string;
}

export interface Slot {
  start: string;
  end: string;
  /** 0 to 100. Higher is better. */
  score: number;
  reason: string;
}

export interface Interval {
  start: string;
  end: string;
  label?: string;
}

export interface PipelineRow extends QuoteItem {
  stage: Stage;
}

export interface Persona {
  name: string;
  style: string;
  greeting: string;
  service_question: string;
  closing: string;
}

export interface PersonasResponse {
  personas: Record<string, Persona>;
  active: string;
}

export const PERSONA_LIMITS: Record<keyof Persona, number> = {
  name: 40,
  style: 300,
  greeting: 200,
  service_question: 200,
  closing: 300,
};

export interface AppEvent {
  ts: string | null;
  kind: string;
  ok: boolean;
  detail: string;
}

export type WorkerState = "ready" | "waking" | "down";

export interface ModelHealth {
  state: WorkerState;
  label: string;
  detail: string;
}

export interface WhatsAppLink {
  number: string | null;
  status: "unlinked" | "pending" | "linked";
}

export type BookingStatus = "confirmed" | "tentative" | "cancelled";

export interface Booking {
  id: string;
  user_id: string;
  customer: string;
  phone?: string;
  address: string;
  start: string; // ISO
  end: string; // ISO
  status: BookingStatus;
  quote_status: QuoteStatus | "none";
  quote_total?: number | null;
  /** Set for events that come from Google Calendar rather than Gesir. */
  source?: "google";
  link?: string;
}

export interface BookingInput {
  user_id: string;
  customer: string;
  phone?: string;
  address: string;
  start: string;
  end: string;
}



