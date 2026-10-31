import { Route, Routes, Navigate } from "react-router-dom";
import Shell from "./Shell";
import Quotes from "./pages/Quotes";
import Calendar from "./pages/Calendar";
import Pipeline from "./pages/Pipeline";
import Customers from "./pages/Customers";
import Dashboard from "./pages/Dashboard";
import Users from "./pages/Users";
import Wallet from "./pages/Wallet";
import OrgSettings from "./pages/OrgSettings";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/app" replace />} />
      <Route path="/app" element={<Shell />}>
        <Route index element={<Dashboard />} />
        <Route path="users" element={<Users />} />
        <Route path="wallet" element={<Wallet />} />
        <Route path="settings" element={<OrgSettings />} />
        <Route path="quotes" element={<Navigate to="/app/pipeline" replace />} />
        <Route path="quotes/:userId" element={<Quotes />} />
        <Route path="pipeline" element={<Pipeline />} />
        <Route path="customers" element={<Customers />} />
        <Route path="calendar" element={<Calendar />} />
        <Route path="connect" element={<Navigate to="/app/settings" replace />} />
        <Route path="personas" element={<Navigate to="/app/settings?tab=personas" replace />} />
        <Route path="status" element={<Navigate to="/app/settings?tab=status" replace />} />
      </Route>
      <Route path="*" element={<Navigate to="/app" replace />} />
    </Routes>
  );
}

