import { mockApi } from "./mock";
import type { AuditEntry, Interval, ParamValue, PdfPreview, PipelineRow, QuoteDetail, Recalculation, Slot } from "./types";
import type {
  AppEvent,
  Booking,
  BookingInput,
  Customer,
  ModelHealth,
  Persona,
  PersonasResponse,
  QuoteItem,
  QuoteStatus,
  WhatsAppLink,
} from "./types";

export interface ApiConfig {
  /** "" means same origin (web dev proxy). Full URL for the mobile app. */
  baseUrl: string;
  /** Mobile only. On web, the proxy adds the key so it never ships in the bundle. */
  apiKey?: string;
  /** Serve everything from in-memory sample data. */
  mock: boolean;
  /** Flip on once the backend has /api/bookings. Until then bookings use sample data. */
  bookingsLive: boolean;
}

let config: ApiConfig = { baseUrl: "", mock: true, bookingsLive: false };

export function configureApi(next: Partial<ApiConfig>) {
  config = { ...config, ...next };
}

export function apiMode(): "mock" | "live" {
  return config.mock ? "mock" : "live";
}

/** Who is acting in the Orbyte-style dashboard. The role goes to the backend, which decides what it may do. */
export interface HubUser {
  id: string;
  name: string;
  email: string;
  role: string;
  approver: boolean;
  reviewer: boolean;
  module_role: "admin" | "approver" | "reviewer";
}
export interface WalletInfo {
  credits: number;
  transactions: { at: number; type: string; change: number; balance: number; details: string }[];
}
let actor: { role: string; name: string } | null = null;
export function setActor(next: { role: string; name: string } | null) {
  actor = next;
}
const SAMPLE_USERS: HubUser[] = [
  { id: "azer", name: "Azer Hamdaoui", email: "", role: "Company Admin", approver: false, reviewer: false, module_role: "admin" },
  { id: "omar", name: "Omar Bouhlel", email: "", role: "Member", approver: true, reviewer: false, module_role: "approver" },
  { id: "tarek", name: "Tarek Ben Slimen", email: "", role: "Member", approver: false, reviewer: true, module_role: "reviewer" },
];

/** Where to load a customer photo from. The backend gives "/api/media/<id>", which the web dashboard loads with its
 * session cookie; the mobile app needs the full server address and its API key on the image request. */
export function mediaSource(url: string): { uri: string; headers?: Record<string, string> } {
  const uri = /^https?:\/\//.test(url) || !config.baseUrl ? url : `${config.baseUrl.replace(/\/$/, "")}${url}`;
  return config.apiKey ? { uri, headers: { "x-api-key": config.apiKey } } : { uri };
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** Plain-language message for each documented failure. */
export function explainError(e: unknown): string {
  const status = (e as { status?: number })?.status;
  switch (status) {
    case 401:
      return "The API key was rejected. Check the key in your settings.";
    case 409:
      return "Nothing is waiting for this customer. It may already be approved.";
    case 422:
      return "That total is not valid. Enter an amount above zero.";
    case 502:
      return "WhatsApp did not send the message. Free replies only work within 24 hours of the customer's last message. Try again, or ask the customer to message first.";
    case 404:
      return "The server does not offer this yet. Ask the backend owner to add it.";
    case 503:
      return "WhatsApp sending is not set up on the server yet.";
    case 0:
      return "Cannot reach the server. Check your connection.";
    default:
      return (e as Error)?.message || "Something went wrong.";
  }
}

async function http<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (config.apiKey) headers["x-api-key"] = config.apiKey;
  if (actor) {
    headers["x-orbyte-role"] = actor.role;
    headers["x-orbyte-user"] = actor.name;
  }
  if (body !== undefined) headers["content-type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(`${config.baseUrl}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Network error");
  }
  if (res.status === 401 && !config.apiKey && !config.mock && typeof window !== "undefined" && typeof window.location?.assign === "function") {
    // Hosted web dashboard: the session cookie is missing or expired, so go to the password page and come back.
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`);
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : msg;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, msg);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Mock errors carry a status too; unify them so screens handle one type. */
async function guard<T>(fn: () => Promise<T>): Promise<T> {
  try {
    return await fn();
  } catch (e) {
    const s = (e as { status?: number }).status;
    if (e instanceof ApiError || s == null) throw e;
    throw new ApiError(s, (e as Error).message);
  }
}

const toArray = <T>(v: unknown, key: string): T[] =>
  Array.isArray(v) ? (v as T[]) : Array.isArray((v as Record<string, unknown>)?.[key]) ? ((v as Record<string, T[]>)[key]) : [];

export const api = {
  listQuotes(status?: QuoteStatus): Promise<QuoteItem[]> {
    if (config.mock) return guard(() => mockApi.listQuotes(status));
    const q = status ? `?status=${status}` : "";
    return http<unknown>("GET", `/api/quotes${q}`).then((r) => toArray<QuoteItem>(r, "quotes"));
  },

  approveQuote(userId: string, total?: number): Promise<unknown> {
    if (config.mock) return guard(() => mockApi.approveQuote(userId, total));
    return http("POST", `/api/quotes/${encodeURIComponent(userId)}/approve`, total != null ? { total } : undefined);
  },

  /** Says no to an estimate: nothing is sent to the customer, the reason is kept in the activity log. Editing the values brings it back. */
  rejectQuote(userId: string, reason: string): Promise<unknown> {
    if (config.mock) return guard(() => mockApi.rejectQuote(userId, reason));
    return http("POST", `/api/quotes/${encodeURIComponent(userId)}/reject`, { reason });
  },

  /** The phone tells the backend where to send push notifications (a customer needs the owner, a quote waits). */
  /** Sends a test notification to every registered phone. */
  testPush(): Promise<unknown> {
    if (config.mock) return guard(async () => ({ sent: 1 }));
    return http("POST", "/api/push/test");
  },

  registerPush(token: string, platform: string): Promise<unknown> {
    if (config.mock) return guard(async () => ({ registered: true }));
    return http("POST", "/api/push/register", { token, platform });
  },

  listPersonas(): Promise<PersonasResponse> {
    if (config.mock) return guard(() => mockApi.listPersonas());
    return http("GET", "/api/personas");
  },

  savePersona(id: string, body: Persona): Promise<unknown> {
    if (config.mock) return guard(() => mockApi.savePersona(id, body));
    return http("PUT", `/api/personas/${encodeURIComponent(id)}`, body);
  },

  setActivePersona(id: string): Promise<unknown> {
    if (config.mock) return guard(() => mockApi.setActivePersona(id));
    return http("POST", "/api/personas/active", { id });
  },

  async hubUsers(): Promise<HubUser[]> {
    if (config.mock) return SAMPLE_USERS;
    return toArray<HubUser>(await http<unknown>("GET", "/api/hub/users"), "users");
  },

  async wallet(): Promise<WalletInfo> {
    if (config.mock) return { credits: 100, transactions: [] };
    return http<WalletInfo>("GET", "/api/wallet");
  },

  async listEvents(limit = 50): Promise<AppEvent[]> {
    if (config.mock) return guard(() => mockApi.listEvents(limit));
    const raw = await http<unknown>("GET", `/api/events?limit=${limit}`);
    return toArray<Record<string, unknown>>(raw, "events").map(normalizeEvent);
  },

  async modelHealth(): Promise<ModelHealth> {
    if (config.mock) return guard(() => mockApi.modelHealth());
    try {
      return normalizeHealth(await http<unknown>("GET", "/api/models/health"));
    } catch (e) {
      if ((e as ApiError).status === 401) throw e;
      return { state: "down", label: "Unreachable", detail: explainError(e) };
    }
  },

  // ---- Review, pipeline and slot endpoints. Paths below are the assumed contract; change them in one place if the backend differs. ----

  getQuoteDetail(userId: string): Promise<QuoteDetail> {
    if (config.mock) return guard(() => mockApi.getQuoteDetail(userId));
    return http("GET", `/api/quotes/${encodeURIComponent(userId)}`);
  },

  /** Backend runs the calculation engine. The UI never computes prices. */
  recalculate(userId: string, params: Record<string, ParamValue>): Promise<Recalculation> {
    if (config.mock) return guard(() => mockApi.recalculate(userId, params));
    return http("POST", `/api/quotes/${encodeURIComponent(userId)}/recalculate`, { params });
  },

  saveParams(userId: string, params: Record<string, ParamValue>): Promise<unknown> {
    if (config.mock) return guard(() => mockApi.saveParams(userId, params));
    return http("PUT", `/api/quotes/${encodeURIComponent(userId)}/params`, { params });
  },

  /** The owner writes to the customer in the assistant's place; the assistant then stays quiet for 30 minutes. */
  sendOwnerMessage(userId: string, text: string): Promise<unknown> {
    if (config.mock) return guard(async () => ({ sent: true }));
    return http("POST", `/api/quotes/${encodeURIComponent(userId)}/message`, { text });
  },

  resumeAssistant(userId: string): Promise<unknown> {
    if (config.mock) return guard(async () => ({ resumed: true }));
    return http("POST", `/api/quotes/${encodeURIComponent(userId)}/resume`);
  },

  /** After the site visit: sends the customer the final price. The backend refuses unless the estimate was approved. */
  confirmFinal(userId: string, total: number): Promise<unknown> {
    if (config.mock) return guard(() => mockApi.confirmFinal(userId, total));
    return http("POST", `/api/quotes/${encodeURIComponent(userId)}/final`, { total });
  },

  /** Every customer with all their jobs, earlier and current. */
  async listCustomers(): Promise<Customer[]> {
    if (config.mock) return guard(() => mockApi.listCustomers());
    const r = await http<{ customers: Customer[] }>("GET", "/api/customers");
    return r.customers;
  },

  pdfPreview(userId: string, params: Record<string, ParamValue>): Promise<PdfPreview> {
    if (config.mock) return guard(() => mockApi.pdfPreview(userId, params));
    return http("POST", `/api/quotes/${encodeURIComponent(userId)}/pdf`, { params });
  },

  async listPipeline(): Promise<PipelineRow[]> {
    if (config.mock) return guard(() => mockApi.listPipeline());
    return toArray<PipelineRow>(await http<unknown>("GET", "/api/pipeline"), "quotes");
  },

  async listActivity(limit = 20): Promise<(AuditEntry & { user_id: string; customer: string })[]> {
    if (config.mock) return guard(() => mockApi.listActivity(limit));
    return toArray(await http<unknown>("GET", `/api/audit?limit=${limit}`), "entries");
  },

  /** `busy` is sent so the backend can treat Google events the browser knows about as taken. */
  async suggestSlots(userId: string, busy: Interval[] = []): Promise<Slot[]> {
    if (config.mock) return guard(() => mockApi.suggestSlots(userId, busy));
    return toArray<Slot>(await http<unknown>("POST", `/api/quotes/${encodeURIComponent(userId)}/slots`, { busy }), "slots");
  },

  /** Planned endpoints, not on the backend yet: GET /api/whatsapp/status, POST /api/whatsapp/link, DELETE /api/whatsapp/link. */
  whatsappStatus(): Promise<WhatsAppLink> {
    if (config.mock) return guard(() => mockApi.whatsappStatus());
    return http("GET", "/api/whatsapp/status");
  },

  linkWhatsapp(number: string): Promise<WhatsAppLink> {
    if (config.mock) return guard(() => mockApi.linkWhatsapp(number));
    return http("POST", "/api/whatsapp/link", { number });
  },

  unlinkWhatsapp(): Promise<unknown> {
    if (config.mock) return guard(() => mockApi.unlinkWhatsapp());
    return http("DELETE", "/api/whatsapp/link");
  },

  listBookings(from: string, to: string): Promise<Booking[]> {
    if (!config.mock && config.bookingsLive) {
      return http<unknown>("GET", `/api/bookings?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`).then(
        (r) => toArray<Booking>(r, "bookings"),
      );
    }
    return guard(() => mockApi.listBookings(from, to));
  },

  createBooking(input: BookingInput): Promise<Booking> {
    if (!config.mock && config.bookingsLive) return http("POST", "/api/bookings", input);
    return guard(() => mockApi.createBooking(input));
  },

  updateBooking(id: string, patch: Partial<Pick<Booking, "start" | "end" | "status">> & { hours?: number }): Promise<Booking> {
    if (!config.mock && config.bookingsLive) return http("PATCH", `/api/bookings/${id}`, patch);
    return guard(() => mockApi.updateBooking(id, patch));
  },

  deleteBooking(id: string): Promise<void> {
    if (!config.mock && config.bookingsLive) return http("DELETE", `/api/bookings/${id}`);
    return guard(() => mockApi.deleteBooking(id));
  },
};

function normalizeEvent(e: Record<string, unknown>): AppEvent {
  const ts = (e.ts ?? e.time ?? e.timestamp ?? e.created_at ?? null) as string | null;
  const kind = String(e.kind ?? e.type ?? e.event ?? "event");
  const detail = String(e.detail ?? e.message ?? e.msg ?? JSON.stringify(e));
  const ok = e.ok === false || /fail|error/i.test(kind) || /fail|error/i.test(String(e.status ?? "")) ? false : true;
  return { ts, kind, ok, detail };
}

function normalizeHealth(raw: unknown): ModelHealth {
  const text = JSON.stringify(raw ?? {}).toLowerCase();
  if (/cold|starting|initializ|waking|loading|throttled/.test(text)) {
    return { state: "waking", label: "Waking up", detail: "Models are starting. This takes 2 to 5 minutes." };
  }
  if (/error|unhealthy|down|fail/.test(text)) {
    return { state: "down", label: "Problem", detail: JSON.stringify(raw).slice(0, 160) };
  }
  return { state: "ready", label: "Ready", detail: JSON.stringify(raw).slice(0, 160) };
}

