import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// `npm run dev` proxies /api, /ws and /healthz to the SIGNOPSIS FastAPI backend (VITE_BACKEND_ORIGIN),
// so the browser talks to one origin and no CORS setup is needed.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backend = env.VITE_BACKEND_ORIGIN || "http://127.0.0.1:8000";
  const single = mode === "single";
  return {
    base: "./",
    plugins: [react(), tailwindcss(), ...(single ? [viteSingleFile()] : [])],
    server: {
      port: 5173,
      proxy: {
        "/api": { target: backend, changeOrigin: true },
        "/healthz": { target: backend, changeOrigin: true },
        "/ws": { target: backend.replace(/^http/, "ws"), ws: true },
      },
    },
    build: {
      outDir: single ? "dist-single" : "dist",
      chunkSizeWarningLimit: 2000,
    },
  };
});
