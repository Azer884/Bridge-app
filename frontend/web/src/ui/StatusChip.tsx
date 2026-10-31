import { ORBYTE_LABEL, orbyteState } from "@shared/params";

const LABEL: Record<string, string> = {
  pending_approval: "Waiting for you",
  approved: "Sent to customer",
  needs_inspection: "Needs inspection",
  tentative: "Tentative",
  confirmed: "Confirmed",
  cancelled: "Cancelled",
  none: "No quote",
};


/** Where the quote sits in Orbyte: staged in the Hub while it waits for the owner, synced to the CRM once approved. */
export function OrbyteChip({ q }: { q: { status: string; orbyte?: "staged" | "synced" | null; revising?: boolean } }) {
  const s = orbyteState(q);
  if (!s) return null;
  return (
    <span className={`orbyte-chip ${s}`} title={s === "staged" ? "Waiting in Orbyte Hub for your approval" : "Recorded in Orbyte CRM"}>
      <span className="orbyte-hex" aria-hidden="true" />
      {ORBYTE_LABEL[s]}
    </span>
  );
}

export function StatusChip({ status }: { status: string }) {
  return <span className={`status-chip ${status}`}>{LABEL[status] ?? status}</span>;
}

export const STATUS_COLOR: Record<string, string> = {
  pending_approval: "var(--tape)",
  approved: "var(--ok)",
  needs_inspection: "var(--danger)",
};

export const BREAKDOWN_COLORS = ["#129a8d", "#59c793", "#083c57", "#3fb5c8", "#e9b949", "#6b8290"];

