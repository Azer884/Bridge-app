import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// The API key lives in API_KEY (no VITE_ prefix), so it never reaches the browser bundle.
// The dev and preview servers add it to proxied /api calls.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.API_URL || "https://Gesir-AI.replit.app";
  const proxy = {
    "/api": {
      target,
      changeOrigin: true,
      secure: true,
      headers: env.API_KEY ? { "x-api-key": env.API_KEY } : {},
    },
  };
  return {
    plugins: [react()],
    resolve: { alias: { "@shared": path.resolve(__dirname, "../shared") } },
    server: { port: 5173, proxy, fs: { allow: [path.resolve(__dirname, "..")] } },
    preview: { proxy },
  };
});
