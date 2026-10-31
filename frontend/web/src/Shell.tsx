import { useEffect, useMemo, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { api, setActor } from "@shared/api";
import { useAsync } from "./hooks";
import { ActorContext } from "./actor";
import type { JSX } from "react";
import { IBriefcase, IBuilding, ICalendar, IChevron, IChevronDown, IFolder, IGear, IHome, IMail, IPen, ISearch, IUserEdit, IUsers, IWallet } from "./ui/ObIcons";

const STORE_KEY = "gesir_actor";

type Icon = () => JSX.Element;
type Item = { to: string; label: string; icon: Icon } | { label: string; icon: Icon; dim: true } | { label: string; icon: Icon; folder: true };

const MENU: { group: string; key: string; icon: Icon; items: Item[] }[] = [
  {
    group: "Organization",
    key: "org",
    icon: IBuilding,
    items: [
      { to: "/app/customers", label: "Clients", icon: IUsers },
      { to: "/app/pipeline", label: "Projects", icon: IFolder },
      { to: "/app/users", label: "Users", icon: IUsers },
      { label: "Profile Change Requests", icon: IUserEdit, dim: true },
      { to: "/app/wallet", label: "Wallet", icon: IWallet },
      { to: "/app/settings", label: "Organization Settings", icon: IBuilding },
      { label: "Email Broadcast", icon: IMail, dim: true },
    ],
  },
  {
    group: "Workspace",
    key: "work",
    icon: IBriefcase,
    items: [{ to: "/app/calendar", label: "Job Calendar", icon: ICalendar }],
  },
  { group: "Talent Hub", key: "talent", icon: IUsers, items: [] },
];
const LATER: [string, Icon][] = [["Reports", IFolder], ["Settings", IGear], ["Orbyte eSign", IPen]];

export default function Shell() {
  const users = useAsync(() => api.hubUsers(), []);
  const pending = useAsync(() => api.listQuotes("pending_approval"), [], 20_000);
  const [chosen, setChosen] = useState(() => localStorage.getItem(STORE_KEY) || "");
  const [open, setOpen] = useState<Record<string, boolean>>({ org: true, work: true });
  const [search, setSearch] = useState("");
  const [picker, setPicker] = useState(false);
  const location = useLocation();
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {          // "/" jumps to the menu search, as in Orbyte
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) && !t.isContentEditable) {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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
  const initials = (me?.name ?? "G").split(" ").map((w) => w[0]).join("").slice(0, 2);
  // the web server reads Gesir's own data, so there is one organization: this business
  return (
    <ActorContext.Provider value={ctx}>
      <div className="shell ob">
        <aside className="side">
          <NavLink to="/app" className="brand" aria-label="Gesir dashboard">
            <img className="brand-mark" src="/logo.png" alt="" />
            Gesir
          </NavLink>
          <div className="org">
            <span className="org-ico"><IBuilding /></span>
            <span className="org-txt"><label>Current organization</label><b>Gesir</b></span>
            <IChevronDown />
          </div>
          <label className="menu-search">
            <ISearch />
            <input ref={searchRef} placeholder="Search menu..." value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search menu" />
            <kbd>/</kbd>
          </label>
          <nav className="nav" aria-label="Main">
            <div className="nav-label">Navigation</div>
            <NavLink to="/app" end className={() => `grp${location.pathname === "/app" ? " on" : ""}`}>
              <IHome />
              <span className="lbl">Dashboard</span>
              {count > 0 && <span className="count" aria-label={`${count} waiting`}>{count}</span>}
              <IChevron />
            </NavLink>
            {MENU.map((g) => {
              const items = g.items.filter((i) => !filter || i.label.toLowerCase().includes(filter));
              if (filter && !items.length && !g.group.toLowerCase().includes(filter)) return null;
              const expanded = (open[g.key] || !!filter) && g.items.length > 0;
              const here = g.items.some((i) => "to" in i && location.pathname.startsWith(i.to));
              return (
                <div key={g.key}>
                  <button type="button" className={`grp${here ? " on" : ""}${g.items.length ? "" : " dim"}`} aria-expanded={expanded}
                    onClick={() => g.items.length && setOpen({ ...open, [g.key]: !open[g.key] })}>
                    <g.icon />
                    <span className="lbl">{g.group}</span>
                    <IChevron open={expanded} />
                  </button>
                  {expanded &&
                    items.map((i) =>
                      "folder" in i ? (
                        <div key={i.label} className="item folder"><i.icon />{i.label}</div>
                      ) : "dim" in i ? (
                        <div key={i.label} className="item dim"><i.icon />{i.label}</div>
                      ) : (
                        <NavLink key={i.to} to={i.to} className={({ isActive }) => `item${isActive || location.pathname.startsWith(i.to) ? " on" : ""}`}>
                          <i.icon />
                          {i.label}
                        </NavLink>
                      ),
                    )}
                </div>
              );
            })}
            {LATER.map(([l, Ico]) => (
              <div key={l} className="grp dim"><Ico /><span className="lbl">{l}</span><IChevron /></div>
            ))}
          </nav>
          <div className="user" onClick={() => setPicker(!picker)} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && setPicker(!picker)}>
            <div className="av">{initials}<i className="online" /></div>
            <div title={me ? `${me.role}, acts as ${me.module_role}` : ""}>
              <b>{me?.name ?? "Signed in"}</b>
              <small>{me ? me.email || `${me.role}${me.approver ? ", Approver" : me.reviewer ? ", Reviewer" : ""}` : ""}</small>
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
