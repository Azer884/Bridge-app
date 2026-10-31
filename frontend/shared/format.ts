import { splitE164 } from "./countries";

export function money(value: number | null | undefined, currency = "MYR"): string {
  if (value == null) return "No price";
  return new Intl.NumberFormat("en-MY", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
  }).format(value);
}

export function phone(raw: string | undefined): string {
  if (!raw) return "No number";
  const d = raw.replace(/\D/g, "");
  const { country, national } = splitE164(d);
  if (!country) return raw;
  if (country.dial === "60" && national.length >= 8) {
    return `+60 ${national.slice(0, 2)}-${national.slice(2, 5)} ${national.slice(5)}`;
  }
  return `+${country.dial} ${national}`;
}

export function timeAgo(iso: string | undefined | null, now = Date.now()): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 60) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  return `${Math.round(h / 24)} d ago`;
}

export function roomSummary(job: {
  room_length_m?: number;
  room_width_m?: number;
  room_height_m?: number;
}): string {
  const { room_length_m: l, room_width_m: w, room_height_m: h } = job;
  if (!l || !w) return "Not given";
  return `${l} × ${w}${h ? ` × ${h}` : ""} m`;
}

export function slotLabel(startIso: string, endIso: string): string {
  const s = new Date(startIso);
  const e = new Date(endIso);
  const t = (d: Date) =>
    d.toLocaleTimeString("en-MY", { hour: "numeric", minute: "2-digit", hour12: true });
  return `${t(s)} – ${t(e)}`;
}


/** "Repaint" or "Aircon service": what the project is, from the job's trade. */
export function jobTitle(job?: { trade?: string | null } | null): string {
  return job?.trade === "aircon" ? "Aircon service" : "Repaint";
}

/** One line on what the job is: the surfaces for painting; the service, units and horsepower for aircon. */
export function jobSummary(job?: { trade?: string | null; surfaces?: string; service_type?: string; unit_count?: string; horsepower?: string } | null): string {
  if (!job) return "Not given";
  if (job.trade === "aircon") {
    const parts = [job.service_type, job.unit_count ? `${job.unit_count} ${Number(job.unit_count) === 1 ? "unit" : "units"}` : "", job.horsepower].filter(Boolean);
    return parts.length ? parts.join(", ") : "Not given";
  }
  return job.surfaces ?? "Not given";
}
