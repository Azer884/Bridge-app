import { Link } from "react-router-dom";
import { api, explainError } from "@shared/api";
import { money, phone } from "@shared/format";
import { useAsync } from "../hooks";

export default function Customers() {
  const { data, error, loading, reload } = useAsync(() => api.listCustomers(), [], 30_000);
  const list = data ?? [];

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Customers</h1>
          <p>Everyone Gesir has talked to, with every job they have had. Open a customer to see the chat and the quote.</p>
        </div>
      </div>

      {error != null && <div className="alert">{explainError(error)}<button className="btn small" onClick={reload}>Try again</button></div>}
      {loading && !data && <div className="panel empty">Loading customers…</div>}
      {data && list.length === 0 && (
        <div className="panel empty"><b>No customers yet</b>They appear here after their first WhatsApp message.</div>
      )}

      <div className="list">
        {list.map((c) => (
          <Link key={c.user_id} to={`/app/quotes/${c.user_id}`} className="row-chip" style={{ textDecoration: "none", color: "inherit" }}>
            <span className="strip" style={{ ["--c" as string]: c.needs_human || c.attention ? "var(--tape)" : undefined }} />
            <span className="body">
              <b>{c.name ?? "Unnamed customer"}</b>
              <small>
                {phone(c.phone ?? c.user_id)} · {c.orders.length} {c.orders.length === 1 ? "job" : "jobs"}
                {(c.needs_human || c.attention) && " · Needs you"}
              </small>
            </span>
            <span className="amt">
              {(() => {
                const last = c.orders[c.orders.length - 1]?.quote;
                const t = last?.final_total ?? last?.approved_total ?? last?.total;
                return last && t != null ? money(t, last.currency) : <small>No price yet</small>;
              })()}
            </span>
          </Link>
        ))}
      </div>
    </>
  );
}
