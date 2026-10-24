import { useSyncExternalStore } from "react";
import { apiMode } from "@shared/api";
import type { Booking } from "@shared/types";

/**
 * Google Calendar from the browser, using Google Identity Services (token flow).
 * - VITE_GOOGLE_CLIENT_ID set: real Google account, events API.
 * - No client id, sample-data mode: demo, nothing leaves the browser.
 * - Otherwise: unavailable.
 * For production, move this to the backend so refresh tokens and secrets stay server-side.
 */
const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined;
const SCOPE = "https://www.googleapis.com/auth/calendar.events";
const API = "https://www.googleapis.com/calendar/v3/calendars/primary/events";

export type GoogleMode = "real" | "demo" | "off";
export const googleMode = (): GoogleMode => (CLIENT_ID ? "real" : apiMode() === "mock" ? "demo" : "off");

let token: { value: string; exp: number } | null = null;
let connected = false;
const subs = new Set<() => void>();
const set = (v: boolean) => {
  connected = v;
  subs.forEach((f) => f());
};

export function useGoogle() {
  const c = useSyncExternalStore(
    (f) => (subs.add(f), () => subs.delete(f)),
    () => connected,
  );
  return { connected: c, mode: googleMode(), connect, disconnect };
}

interface TokenClient {
  requestAccessToken: (o?: { prompt?: string }) => void;
}
declare global {
  interface Window {
    google?: {
      accounts: {
        oauth2: {
          initTokenClient: (c: {
            client_id: string;
            scope: string;
            callback: (r: { access_token?: string; expires_in?: number; error?: string }) => void;
          }) => TokenClient;
          revoke: (t: string, done?: () => void) => void;
        };
      };
    };
  }
}

function loadScript(): Promise<void> {
  if (window.google?.accounts) return Promise.resolve();
  return new Promise((res, rej) => {
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true;
    s.onload = () => res();
    s.onerror = () => rej(new Error("Could not load Google sign-in. Check your connection."));
    document.head.appendChild(s);
  });
}

export async function connect(): Promise<void> {
  const mode = googleMode();
  if (mode === "off") throw new Error("Google Calendar is not set up. Add VITE_GOOGLE_CLIENT_ID to the web .env.");
  if (mode === "demo") return set(true);
  await loadScript();
  await new Promise<void>((res, rej) => {
    const client = window.google!.accounts.oauth2.initTokenClient({
      client_id: CLIENT_ID!,
      scope: SCOPE,
      callback: (r) => {
        if (r.error || !r.access_token) return rej(new Error(r.error === "access_denied" ? "Google access was declined." : "Google sign-in failed."));
        token = { value: r.access_token, exp: Date.now() + (r.expires_in ?? 3600) * 1000 - 60_000 };
        res();
      },
    });
    client.requestAccessToken({ prompt: token ? "" : "consent" });
  });
  set(true);
}

export function disconnect() {
  if (token && window.google) window.google.accounts.oauth2.revoke(token.value);
  token = null;
  set(false);
}

async function authed(init: RequestInit & { url: string }): Promise<Response> {
  if (!token || token.exp < Date.now()) await connect();
  const res = await fetch(init.url, { ...init, headers: { ...(init.headers ?? {}), authorization: `Bearer ${token!.value}`, "content-type": "application/json" } });
  if (res.status === 401) {
    token = null;
    set(false);
    throw new Error("Google session ended. Connect Google Calendar again.");
  }
  if (!res.ok) throw new Error(`Google Calendar said ${res.status}.`);
  return res;
}

const DEMO: Booking[] = (() => {
  const at = (d: number, h: number, m: number, mins: number) => {
    const s = new Date();
    s.setDate(s.getDate() + d);
    s.setHours(h, m, 0, 0);
    return { start: s.toISOString(), end: new Date(s.getTime() + mins * 60_000).toISOString() };
  };
  const mk = (id: string, customer: string, d: number, h: number, m: number, mins: number): Booking => ({
    id: `g_${id}`, user_id: "", customer, address: "", ...at(d, h, m, mins), status: "confirmed", quote_status: "none", source: "google",
  });
  return [mk("1", "Dentist", 2, 10, 0, 60), mk("2", "School run", 1, 15, 0, 30), mk("3", "Supplier call", 0, 11, 0, 45)];
})();

/** Other events on the primary calendar (not ones Gesir wrote). */
export async function gList(from: string, to: string): Promise<Booking[]> {
  if (googleMode() === "demo") return DEMO.filter((b) => b.start >= from && b.start < to);
  const p = new URLSearchParams({ timeMin: from, timeMax: to, singleEvents: "true", orderBy: "startTime", maxResults: "250" });
  const res = await authed({ url: `${API}?${p}` });
  const j = (await res.json()) as { items?: GEvent[] };
  return (j.items ?? [])
    .filter((e) => e.status !== "cancelled" && e.start?.dateTime && !e.extendedProperties?.private?.gesirBooking)
    .map((e) => ({
      id: `g_${e.id}`, user_id: "", customer: e.summary ?? "Busy", address: e.location ?? "",
      start: e.start!.dateTime!, end: e.end?.dateTime ?? e.start!.dateTime!,
      status: "confirmed" as const, quote_status: "none" as const, source: "google" as const, link: e.htmlLink,
    }));
}

interface GEvent {
  id: string;
  status?: string;
  summary?: string;
  location?: string;
  htmlLink?: string;
  start?: { dateTime?: string };
  end?: { dateTime?: string };
  extendedProperties?: { private?: Record<string, string> };
}

async function findMirror(id: string): Promise<string | null> {
  const p = new URLSearchParams({ privateExtendedProperty: `gesirBooking=${id}`, maxResults: "1" });
  const res = await authed({ url: `${API}?${p}` });
  const j = (await res.json()) as { items?: GEvent[] };
  return j.items?.[0]?.id ?? null;
}

/** Create or update the Google event that mirrors a Gesir booking. */
export async function gSync(b: Booking): Promise<void> {
  if (googleMode() === "demo") return;
  const body = {
    summary: `${b.customer} (Gesir)`,
    location: b.address,
    description: [b.phone ? `WhatsApp: +${b.phone}` : "", b.quote_total != null ? `Quote: ${b.quote_total}` : ""].filter(Boolean).join("\n"),
    start: { dateTime: b.start },
    end: { dateTime: b.end },
    extendedProperties: { private: { gesirBooking: b.id } },
  };
  const existing = await findMirror(b.id);
  if (existing) await authed({ url: `${API}/${existing}`, method: "PATCH", body: JSON.stringify(body) });
  else await authed({ url: API, method: "POST", body: JSON.stringify(body) });
}

export async function gRemove(bookingId: string): Promise<void> {
  if (googleMode() === "demo") return;
  const existing = await findMirror(bookingId);
  if (existing) await authed({ url: `${API}/${existing}`, method: "DELETE" });
}
