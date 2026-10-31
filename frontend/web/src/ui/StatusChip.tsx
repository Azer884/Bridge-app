const LABEL: Record<string, string> = {
  pending_approval: "Waiting for you",
  approved: "Sent to customer",
  needs_inspection: "Needs inspection",
  rejected: "Rejected",
  tentative: "Tentative",
  confirmed: "Confirmed",
  cancelled: "Cancelled",
  none: "No quote",
};

export function StatusChip({ status }: { status: string }) {
  return <span className={`status-chip ${status}`}>{LABEL[status] ?? status}</span>;
}

export const STATUS_COLOR: Record<string, string> = {
  pending_approval: "var(--tape)",
  approved: "var(--ok)",
  needs_inspection: "var(--danger)",
  rejected: "var(--danger)",
};

export const BREAKDOWN_COLORS = ["#129a8d", "#59c793", "#083c57", "#3fb5c8", "#e9b949", "#6b8290"];

