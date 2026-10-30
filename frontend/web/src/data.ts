import { api } from "@shared/api";
import type { QuoteItem, QuoteStatus } from "@shared/types";

export const QUOTE_STATUSES: QuoteStatus[] = ["pending_approval", "approved", "needs_inspection", "rejected"];

export async function loadAllQuotes(): Promise<QuoteItem[]> {
  const parts = await Promise.all(QUOTE_STATUSES.map((s) => api.listQuotes(s)));
  return parts.flat();
}
