import { Route, Routes, Navigate } from "react-router-dom";
import Landing from "./pages/Landing";
import Shell from "./Shell";
import Quotes from "./pages/Quotes";
import Calendar from "./pages/Calendar";
import Connect from "./pages/Connect";
import Pipeline from "./pages/Pipeline";
import Personas from "./pages/Personas";
import Status from "./pages/Status";
import Customers from "./pages/Customers";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/app" element={<Shell />}>
        <Route index element={<Navigate to="quotes" replace />} />
        <Route path="quotes/:userId?" element={<Quotes />} />
        <Route path="pipeline" element={<Pipeline />} />
        <Route path="customers" element={<Customers />} />
        <Route path="calendar" element={<Calendar />} />
        <Route path="connect" element={<Connect />} />
        <Route path="personas" element={<Personas />} />
        <Route path="status" element={<Status />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

