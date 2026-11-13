import { defineConfig } from "vite";
import { stoaApi } from "./mock/stoaApi";

// `/api/*` → W4's API on :8100 when it is up, else the local mock (see mock/stoaApi.ts).
export default defineConfig({
  plugins: [stoaApi()],
  server: { host: "127.0.0.1", port: 5173 },
  preview: { host: "127.0.0.1", port: 5173 },
  optimizeDeps: { exclude: ["web-ifc"] },
  build: { target: "es2022", chunkSizeWarningLimit: 4000 },
});
