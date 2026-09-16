// Runtime configuration. Everything the frontend needs to find the SIGNOPSIS backend lives here.
// Values come from Vite env vars (see .env.example) and can be overridden at runtime in Settings
// (persisted per browser) or with ?backend=live|mock&api=http://host:8000 in the URL.

const env = import.meta.env || {};
const LS_KEY = "signopsis.backend";

function readStored() {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || "{}"); } catch { return {}; }
}

function readQuery() {
  try {
    const q = new URLSearchParams(window.location.search);
    const o = {};
    if (q.get("backend")) o.mode = q.get("backend");
    if (q.get("api")) o.apiBase = q.get("api");
    if (q.get("ws")) o.wsUrl = q.get("ws");
    return o;
  } catch { return {}; }
}

const stored = readStored();
const query = readQuery();

export const config = {
  /** "mock" | "live" | "auto" */
  mode: query.mode || stored.mode || env.VITE_BACKEND_MODE || "auto",
  /** "" = same origin (Vite dev proxy / backend serving the build) */
  apiBase: (query.apiBase ?? stored.apiBase ?? env.VITE_API_BASE ?? "").replace(/\/$/, ""),
  wsUrl: query.wsUrl ?? stored.wsUrl ?? env.VITE_WS_URL ?? "",
  user: stored.user || env.VITE_DEFAULT_USER || "demo",
  /** request timeout for REST calls */
  timeoutMs: 12000,
};

export function saveConfig(patch) {
  Object.assign(config, patch);
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({ mode: config.mode, apiBase: config.apiBase, wsUrl: config.wsUrl, user: config.user }));
  } catch { /* storage unavailable: keep in memory */ }
}

export function wsUrlFor(path, params) {
  let base = config.wsUrl;
  if (!base) {
    const origin = config.apiBase || window.location.origin;
    base = origin.replace(/^http/, "ws") + path;
  }
  const u = new URL(base, window.location.href);
  Object.entries(params || {}).forEach(([k, v]) => v != null && u.searchParams.set(k, v));
  return u.toString();
}
