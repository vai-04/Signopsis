// The single entry point the UI uses to talk to SIGNOPSIS. Every screen calls `backend.*`;
// whether that goes to the FastAPI server or to the in-browser mock is decided here.
//
//   mode "live" -> REST + WebSocket to the server (see config.js / .env)
//   mode "mock" -> recorded fixtures + mock resolver + MockSignSocket
//   mode "auto" -> GET /healthz once; live if it answers, otherwise mock
import { config, saveConfig } from "../config.js";
import { http } from "./http.js";
import { SignSocket } from "./signSocket.js";
import { mockApi } from "./mock/mockApi.js";
import { describeLocally } from "./screen.js";
import { metrics } from "./metrics.js";
import { MockSignSocket } from "./mock/mockSignSocket.js";

const listeners = new Set();
const state = { resolved: null, checking: false, health: null, error: null, latencyMs: null };

function publish() { listeners.forEach(f => f({ ...state, requested: config.mode })); }

const live = {
  health: () => http("/healthz", { timeoutMs: 2500 }),
  textToSign: (req, signal) => http("/api/text-to-sign", { method: "POST", body: req, signal }),
  sign: gloss => http(`/api/sign/${encodeURIComponent(gloss)}`),
  lexicon: () => http("/api/lexicon"),
  simcam: p => http(`/api/simcam?${new URLSearchParams(Object.entries(p).filter(([, v]) => v !== undefined && v !== ""))}`),
  userSigns: user => http(`/api/users/${encodeURIComponent(user)}/signs`),
  forgetSign: (user, label) => http(`/api/users/${encodeURIComponent(user)}/signs/${encodeURIComponent(label)}`, { method: "DELETE" }),
  getMode: () => http("/api/mode"),
  setMode: mode => http("/api/mode", { method: "POST", body: { mode } }),
  evalReport: () => http("/api/eval/report"),
  describeScreen: req => http("/api/screen/describe", { method: "POST", body: req }),
};

async function impl() {
  if (!state.resolved) await backend.resolve();
  return state.resolved === "live" ? live : mockApi;
}

export const backend = {
  get status() { return { ...state, requested: config.mode }; },
  get isMock() { return state.resolved !== "live"; },

  subscribe(fn) {
    listeners.add(fn);
    fn({ ...state, requested: config.mode });
    return () => listeners.delete(fn);
  },

  /** decide live vs mock (call again after changing settings) */
  async resolve(force = false) {
    if (state.checking && !force) return state.resolved;
    if (config.mode === "mock") {
      Object.assign(state, { resolved: "mock", health: null, error: null });
      publish();
      return "mock";
    }
    state.checking = true;
    publish();
    const t0 = performance.now();
    try {
      state.health = await live.health();
      state.latencyMs = Math.round(performance.now() - t0);
      state.resolved = "live";
      state.error = null;
    } catch (e) {
      state.health = null;
      state.error = e.message || String(e);
      state.resolved = config.mode === "live" ? "live" : "mock";   // live stays live (and shows errors)
    } finally {
      state.checking = false;
      publish();
    }
    return state.resolved;
  },

  async configure(patch) {
    saveConfig(patch);
    return this.resolve(true);
  },

  /** @param {import("../contracts/contracts").TextToSignRequest} req @returns {Promise<import("../contracts/contracts").TextToSignResponse>} */
  async textToSign(req, signal) {
    const t0 = performance.now();
    const res = await (await impl()).textToSign({ seed: 7, resolutions: {}, ...req }, signal);
    const sign = res.plan?.targets?.find(t => t.kind === "sign");
    const gate = res.plan?.gate;
    metrics.record("result", { state: gate === "emit" ? "high" : gate, channel: "text", latency: Math.round(performance.now() - t0), server: res.plan?.timings_ms?.total });
    if (sign) metrics.record("roundtrip", { text: req.text, score: sign.roundtrip_score, perGloss: sign.gloss.map(g => ({ g: g.g, rt: g.roundtrip, fs: g.fingerspelled })) });
    return res;
  },
  /** @returns {Promise<import("../contracts/contracts").AvatarClip>} */
  async sign(gloss) { return (await impl()).sign(gloss); },
  /** @returns {Promise<import("../contracts/contracts").Lexicon>} */
  async lexicon() { return (await impl()).lexicon(); },
  async simcam(params) { return (await impl()).simcam(params); },
  async userSigns(user = config.user) { return (await impl()).userSigns(user); },
  async forgetSign(label, user = config.user) { return (await impl()).forgetSign(user, label); },
  async getMode() { return (await impl()).getMode(); },
  async setMode(mode) { return (await impl()).setMode(mode); },

  /** trust-model evaluation (reliability bins, confidently-wrong rate by severity) */
  async evalReport() { return (await impl()).evalReport(); },

  /**
   * Pipeline E: describe a screen. Live servers without the endpoint fall back to the local describer.
   * @param {{question: string, intent?: string, snapshot: any}} req
   */
  async describeScreen(req) {
    const api = await impl();
    try {
      return await api.describeScreen(req);
    } catch (e) {
      if (state.resolved === "live" && e.status !== 404) throw e;
      return { ...describeLocally(req), source: "local" };
    }
  },

  /** open a sign->text session; returns an object with on/send/close */
  async openSignSession({ user = config.user, lang = "en", dominant = "right" } = {}) {
    await impl();
    const Sock = state.resolved === "live" ? SignSocket : MockSignSocket;
    return new Sock({ user, lang, dominant }).connect();
  },
};
