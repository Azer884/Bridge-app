import { useMemo, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { api, apiMode, setActor } from "@shared/api";
import { useAsync } from "./hooks";
import { ActorContext } from "./actor";

const STORE_KEY = "gesir_actor";

type Item = { to: string; label: string; end?: boolean } | { label: string; dim: true };

const MENU: { group: string; key: string; items: Item[] }[] = [
  {
    group: "Organization",
    key: "org",
    items: [
      { to: "/app/customers", label: "Clients" },
      { to: "/app/pipeline", label: "Projects" },
      { to: "/app/users", label: "Users" },
      { label: "Profile Change Requests", dim: true },
      { to: "/app/wallet", label: "Wallet" },
      { to: "/app/settings", label: "Organization Settings" },
    ],
  },
  {
    group: "Workspace",
    key: "work",
    items: [
      { to: "/app/quotes", label: "Quotes" },
      { to: "/app/calendar", label: "Calendar" },
      { to: "/app/connect", label: "WhatsApp" },
      { to: "/app/personas", label: "Personas" },
      { to: "/app/status", label: "Status" },
    ],
  },
];

export default function Shell() {
  const users = useAsync(() => api.hubUsers(), []);
  const pending = useAsync(() => api.listQuotes("pending_approval"), [], 20_000);
  const health = useAsync(() => api.modelHealth(), [], 15_000);
  const [chosen, setChosen] = useState(() => localStorage.getItem(STORE_KEY) || "");
  const [open, setOpen] = useState<Record<string, boolean>>({ org: true, work: true });
  const [search, setSearch] = useState("");
  const [picker, setPicker] = useState(false);
  const location = useLocation();

  const list = users.data ?? [];
  const me = list.find((u) => u.id === chosen) ?? list[0] ?? null;
  // set before the pages below fetch, so their first request already carries the role
  setActor(me ? { role: me.module_role, name: me.name } : null);
  const ctx = useMemo(
    () => ({ users: list, me, choose: (id: string) => { localStorage.setItem(STORE_KEY, id); setChosen(id); setPicker(false); } }),
    [list, me],
  );

  const count = pending.data?.length ?? 0;
  const filter = search.trim().toLowerCase();
  const state = health.data?.state ?? "waking";
  const initials = (me?.name ?? "G").split(" ").map((w) => w[0]).join("").slice(0, 2);
  // the web server reads Gesir's own data, so there is one organization: this business
  return (
    <ActorContext.Provider value={ctx}>
      <div className="shell ob">
        <aside className="side">
          <NavLink to="/" className="brand" aria-label="Gesir home">
            <img className="brand-mark" src="/logo.png" alt="" />
            Gesir
            <small>on Orbyte</small>
          </NavLink>
          <div className="org">
            <label>Current organization</label>
            <b>Gesir</b>
          </div>
          <input className="menu-search" placeholder="Search menu..." value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search menu" />
          <nav className="nav" aria-label="Main">
            <div className="nav-label">Navigation</div>
            <NavLink to="/app" end className={() => `grp leaf${location.pathname === "/app" ? " active" : ""}`}>Dashboard</NavLink>
            {MENU.map((g) => {
              const items = g.items.filter((i) => !filter || i.label.toLowerCase().includes(filter));
              if (filter && !items.length) return null;
              const expanded = open[g.key] || !!filter;
              return (
                <div key={g.key}>
                  <button type="button" className="grp" aria-expanded={expanded} onClick={() => setOpen({ ...open, [g.key]: !open[g.key] })}>
                    {g.group}
                    <span aria-hidden>{expanded ? "⌄" : "›"}</span>
                  </button>
                  {expanded &&
                    items.map((i) =>
                      "dim" in i ? (
                        <div key={i.label} className="item dim">{i.label}</div>
                      ) : (
                        <NavLink key={i.to} to={i.to} className="item">
                          {i.label}
                          {i.to === "/app/quotes" && count > 0 && <span className="count" aria-label={`${count} waiting`}>{count}</span>}
                        </NavLink>
                      ),
                    )}
                </div>
              );
            })}
            {["Talent Hub", "Reports", "Settings", "Orbyte eSign"].map((l) => (
              <div key={l} className="grp dim">{l}<span aria-hidden>›</span></div>
            ))}
          </nav>
          <div className="side-foot">
            <span className="pill"><span className={`dot ${state}`} />{health.data?.label ?? "Checking models"}</span>
            <span>{apiMode() === "mock" ? "Showing sample data" : "Connected to live backend"}</span>
          </div>
          <div className="user" onClick={() => setPicker(!picker)} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && setPicker(!picker)}>
            <div className="av">{initials}</div>
            <div>
              <b>{me?.name ?? "Signed in"}</b>
              <small>{me ? `${me.role}${me.approver ? " · Approver" : me.reviewer ? " · Reviewer" : ""}` : ""}</small>
            </div>
            {picker && (
              <div className="pop" onClick={(e) => e.stopPropagation()}>
                <div className="h">Act as (simulated users)</div>
                {list.map((u) => (
                  <button key={u.id} type="button" className="o" onClick={() => ctx.choose(u.id)}>
                    <span>{u.name}</span>
                    <small>{u.module_role}</small>
                  </button>
                ))}
              </div>
            )}
          </div>
        </aside>
        <main className="main">
          <Outlet />
        </main>
      </div>
    </ActorContext.Provider>
  );
}
