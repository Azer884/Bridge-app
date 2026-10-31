import { Link } from "react-router-dom";
import { api, explainError } from "@shared/api";
import { money, phone } from "@shared/format";
import { useAsync } from "../hooks";

/** Orbyte's Client List: everyone Gesir has talked to, with their jobs. */
export default function Customers() {
  const { data, error, loading, reload } = useAsync(() => api.listCustomers(), [], 30_000);
  const list = data ?? [];

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Client List</h1>
          <p>Manage client records and open each client's project workspace. Open a client to see the chat and the quote.</p>
        </div>
      </div>

      {error != null && <div className="alert">{explainError(error)}<button className="btn small" onClick={reload}>Try again</button></div>}
      {loading && !data && <div className="panel ob-card empty">Loading clients…</div>}
      {data && list.length === 0 && (
        <div className="panel ob-card empty"><b>No clients yet</b>They appear here after their first WhatsApp message.</div>
      )}

      {list.length > 0 && (
        <section className="panel ob-card">
          <table className="ob-table">
            <thead>
              <tr><th>Client</th><th>Phone</th><th>Projects</th><th>Latest price</th><th></th></tr>
            </thead>
            <tbody>
              {list.map((c) => {
                const last = c.orders[c.orders.length - 1]?.quote;
                const t = last?.final_total ?? last?.approved_total ?? last?.total;
                return (
                  <tr key={c.user_id}>
                    <td>
                      <b>{c.name ?? "Name not given yet"}</b>
                      {(c.needs_human || c.attention) && <span className="ob-pill warn" style={{ marginLeft: 8 }}>Needs you</span>}
                    </td>
                    <td className="num">{phone(c.phone ?? c.user_id)}</td>
                    <td>{c.orders.length}</td>
                    <td className="num">{last && t != null ? money(t, last.currency) : "-"}</td>
                    <td><Link className="ob-link" to={`/app/quotes/${c.user_id}`}>Open</Link></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      )}
    </>
  );
}
