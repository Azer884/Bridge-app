import type { ParamField, ParamValue, Interval, Stage, QuoteStatus } from "./types";

/** Client-side input checks from the schema the backend sends. The backend still validates. */
export function validateParams(schema: ParamField[], values: Record<string, ParamValue>): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const f of schema) {
    const v = values[f.key];
    if (f.type === "select") {
      if (!f.options?.some((o) => o.value === v)) errors[f.key] = "Pick an option.";
      continue;
    }
    if (typeof v !== "number" || !Number.isFinite(v)) errors[f.key] = "Enter a number.";
    else if (f.integer && !Number.isInteger(v)) errors[f.key] = "Use a whole number.";
    else if (f.min != null && v < f.min) errors[f.key] = `At least ${f.min}${f.unit ? " " + f.unit : ""}.`;
    else if (f.max != null && v > f.max) errors[f.key] = `At most ${f.max}${f.unit ? " " + f.unit : ""}.`;
  }
  return errors;
}

export const showValue = (f: ParamField, v: ParamValue | undefined): string => {
  if (v == null || v === "") return "Not given";
  if (f.type === "select") return f.options?.find((o) => o.value === v)?.label ?? String(v);
  return `${v}${f.unit ? " " + f.unit : ""}`;
};

export const STAGES: { id: Stage; label: string; hint: string }[] = [
  { id: "pending_extraction", label: "Pending AI extraction", hint: "Gesir is still chatting with the customer." },
  { id: "requires_approval", label: "Needs your approval", hint: "Check the details and send the quote." },
  { id: "quote_sent", label: "Quote sent", hint: "Waiting for the customer." },
  { id: "scheduled", label: "Scheduled and booked", hint: "A slot is booked." },
  { id: "completed", label: "Completed", hint: "Job done." },
  { id: "rejected", label: "Rejected", hint: "Nothing was sent. Change a value to send it back for approval." },
];

/** Fallback when the backend does not send a stage. */
export function fallbackStage(status: QuoteStatus): Stage {
  if (status === "collecting") return "pending_extraction";
  if (status === "approved") return "quote_sent";
  if (status === "completed") return "completed";
  if (status === "rejected") return "rejected";
  return "requires_approval";
}

export function overlaps(a: Interval, b: Interval): boolean {
  return new Date(a.start) < new Date(b.end) && new Date(a.end) > new Date(b.start);
}

/** Events that clash with a chosen window. Used by the double-booking guard. */
export function findConflicts(window: Interval, events: (Interval & { id?: string })[], ignoreId?: string): (Interval & { id?: string })[] {
  return events.filter((e) => e.id !== ignoreId && overlaps(window, e));
}
