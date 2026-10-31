import { api, explainError } from "@shared/api";
import { useAsync } from "../hooks";

export default function Wallet() {
  const { data, error } = useAsync(() => api.wallet(), [], 10_000);
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Wallet</h1>
          <p>Shared organization credits. Each estimate that a person approves uses 1 credit.</p>
        </div>
      </div>
      {error != null && <div className="alert">{explainError(error)}</div>}
      <section className="panel ob-card">
        <small className="ob-kicker">WALLET BALANCE</small>
        <div className="ob-big num">{data?.credits ?? "-"}</div>
        <span className="ob-pill ok">Active</span>
      </section>
      <section className="panel ob-card">
        <h2>Transactions</h2>
        {data && data.transactions.length === 0 && (
          <div className="empty">
            <b>No activity yet</b>Credits are used when an estimate is approved.
          </div>
        )}
        {data && data.transactions.length > 0 && (
          <table className="ob-table">
            <thead>
              <tr><th>Date</th><th>Type</th><th>Change</th><th>Balance</th><th>Details</th></tr>
            </thead>
            <tbody>
              {data.transactions.map((t, i) => (
                <tr key={i}>
                  <td>{new Date(t.at * 1000).toLocaleString([], { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</td>
                  <td>{t.type}</td>
                  <td className="num">{t.change}</td>
                  <td className="num">{t.balance}</td>
                  <td>{t.details}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="note">Assumed rule: Orbyte's own pricing is not public.</p>
      </section>
    </>
  );
}
