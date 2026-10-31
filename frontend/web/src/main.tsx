import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { configureApi } from "@shared/api";
import App from "./App";
import { ToastProvider } from "./ui/Toast";
import "./styles.css";
import "./orbyte.css";

configureApi({
  baseUrl: "",
  mock: import.meta.env.VITE_USE_MOCK !== "false",
  bookingsLive: import.meta.env.VITE_BOOKINGS_LIVE === "true",
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <ToastProvider>
        <App />
      </ToastProvider>
    </BrowserRouter>
  </StrictMode>,
);
