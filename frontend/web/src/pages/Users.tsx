import { useActor } from "../actor";

export default function Users() {
  const { users, me, choose } = useActor();
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Users</h1>
          <p>Who can see and act on quotes. Approving or rejecting needs the Company Admin role or Approver. A Reviewer can only read.</p>
        </div>
      </div>
      <section className="panel ob-card">
        <table className="ob-table">
          <thead>
            <tr><th>User</th><th>Email</th><th>Role</th><th>Approver</th><th>Reviewer</th><th>In Gesir</th><th></th></tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td><b>{u.name}</b></td>
                <td>{u.email || "-"}</td>
                <td>{u.role}</td>
                <td>{u.approver ? "Yes" : "No"}</td>
                <td>{u.reviewer ? "Yes" : "No"}</td>
                <td><span className={`ob-pill ${u.module_role === "reviewer" ? "mute" : "ok"}`}>{u.module_role}</span></td>
                <td>
                  {me?.id === u.id ? (
                    <span className="ob-pill ok">Acting as</span>
                  ) : (
                    <button className="btn small" onClick={() => choose(u.id)}>Act as</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="note">
          Logins are simulated: the team members act as these roles for the demo. The server checks the role on every approve and reject, so a Reviewer is refused even if the button is used.
        </p>
      </section>
    </>
  );
}
