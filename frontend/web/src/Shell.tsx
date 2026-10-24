import { NavLink, Outlet } from "react-router-dom";
import { api, apiMode } from "@shared/api";
import { useAsync } from "./hooks";
import { ThemeToggle } from "./ui/ThemeToggle";
import { IconCalendar, IconChat, IconPipeline, IconPersona, IconQuotes, IconStatus } from "./ui/Icons";

export default function Shell() {
  const pending = useAsync(() => api.listQuotes("pending_approval"), [], 20_000);
  const health = useAsync(() => api.modelHealth(), [], 15_000);
  const count = pending.data?.length ?? 0;
  const state = health.data?.state ?? "waking";

  return (
    <div className="shell">
      <aside className="side">
        <NavLink to="/" className="brand" aria-label="Gesir home">
          <img className="brand-mark" src="/logo.png" alt="" />
          Gesir
        </NavLink>
        <nav className="nav" aria-label="Main">
          <NavLink to="/app/quotes">
            <IconQuotes />
            Quotes
            {count > 0 && <span className="count" aria-label={`${count} waiting`}>{count}</span>}
          </NavLink>
          <NavLink to="/app/pipeline">
            <IconPipeline />
            Pipeline
          </NavLink>
          <NavLink to="/app/calendar">
            <IconCalendar />
            Calendar
          </NavLink>
          <NavLink to="/app/connect">
            <IconChat />
            WhatsApp
          </NavLink>
          <NavLink to="/app/personas">
            <IconPersona />
            Personas
          </NavLink>
          <NavLink to="/app/status">
            <IconStatus />
            Status
          </NavLink>
        </nav>
        <div className="side-foot">
          <span className="pill">
            <span className={`dot ${state}`} />
            {health.data?.label ?? "Checking models"}
          </span>
          <span>{apiMode() === "mock" ? "Showing sample data" : "Connected to live backend"}</span>
        </div>
      </aside>
      <main className="main">
        <div className="topbar">
          <ThemeToggle />
        </div>
        <Outlet />
      </main>
    </div>
  );
}



