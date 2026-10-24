import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { explainError } from "@shared/api";
import { money, phone, timeAgo } from "@shared/format";
import type { QuoteStatus } from "@shared/types";
import { loadAllQuotes } from "../data";
import { useAsync } from "../hooks";
import { QuoteDetail } from "../quote/QuoteDetail";
import { STATUS_COLOR } from "../ui/StatusChip";

const TABS: { id: QuoteStatus; label: string }[] = [
  { id: "pending_approval", label: "Needs your OK" },
  { id: "approved", label: "Approved" },
  { id: "needs_inspection", label: "Inspect" },
];

export default function Quotes() {
  const { userId } = useParams();
  const nav = useNavigate();
  const { data, error, loading, reload } = useAsync(loadAllQuotes, [], 15_000);
  const [tab, setTab] = useState<QuoteStatus>("pending_approval");

  const items = data ?? [];
  const selected = items.find((q) => q.user_id === userId) ?? null;
  const counts = useMemo(
    () => Object.fromEntries(TABS.map((t) => [t.id, items.filter((q) => q.status === t.id).length])),
    [items],
  );
  const visible = items.filter((q) => q.status === tab);

  useEffect(() => {
    if (selected && TABS.some((t) => t.id === selected.status)) setTab(selected.status);
  }, [selected?.user_id]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Quotes</h1>
          <p>Gesir drafted these on your behalf. Nothing reaches the customer until you approve, and they only see the total. <Link to="/app/pipeline" className="link">See every job in the pipeline</Link>.</p>
        </div>
        <div className="tabs" role="tablist" aria-label="Quote status">
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              className="tab"
              aria-selected={tab === t.id}
              onClick={() => {
                setTab(t.id);
                if (selected && selected.status !== t.id) nav("/app/quotes");
              }}
            >
              {t.label}
              <small>{counts[t.id] ?? 0}</small>
            </button>
          ))}
        </div>
      </div>

      {error != null && !data && (
        <div className="alert">
          <span>{explainError(error)}</span>
          <button className="btn small" onClick={reload}>Try again</button>
        </div>
      )}

      <div className={`split${userId ? " has-detail" : ""}`}>
        <div className="list-col">
          {loading && !data ? (
            <div className="empty">Loading quotes…</div>
          ) : visible.length === 0 ? (
            <div className="panel empty">
              <b>{tab === "pending_approval" ? "Nothing waiting" : "Nothing here yet"}</b>
              <span>
                {tab === "pending_approval"
                  ? "New drafts show up here as customers finish their chat."
                  : "Quotes will appear here after you act on them."}
              </span>
            </div>
          ) : (
            <div className="list">
              {visible.map((q) => (
                <Link
                  key={q.user_id}
                  to={`/app/quotes/${q.user_id}`}
                  className="row-chip"
                  aria-current={q.user_id === userId}
                  style={{ "--c": STATUS_COLOR[q.status] } as React.CSSProperties}
                >
                  <span className="strip" />
                  <span className="body">
                    <b>{q.job.name ?? phone(q.job.phone ?? q.user_id)}</b>
                    <small>{q.job.address ?? "No address yet"}</small>
                  </span>
                  <span className="amt num">
                    {q.quote?.total != null ? money(q.quote.total, q.quote.currency) : "Inspect"}
                    <small>{timeAgo(q.updated_at)}</small>
                  </span>
                </Link>
              ))}
            </div>
          )}
        </div>
        <div className="detail-col">
          {userId ? (
            <QuoteDetail key={userId} userId={userId} onChanged={() => void reload()} />
          ) : (
            <div className="panel empty">
              <b>Pick a quote</b>
              <span>What Gesir read, the price, the chat and photos, and the approve button show up here.</span>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
