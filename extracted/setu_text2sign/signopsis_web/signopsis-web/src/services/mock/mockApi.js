// Mock implementations of every backend REST endpoint. Same inputs, same output shapes.
// Recorded fixtures (src/mocks/*.json, exported from the real backend) are used whenever they match;
// anything else goes through the in-browser mock resolver.
import T2S from "../../mocks/t2s.json";
import LEXICON from "../../mocks/lexicon.json";
import EVAL from "../../mocks/eval_report.json";
import { describeLocally } from "../screen.js";
import SIMCAM from "../../mocks/simcam_sample.json";
import { mockTextToSign } from "./mockResolver.js";
import { clipForSign } from "./clipComposer.js";
import { mockState } from "./mockState.js";

const wait = (ms) => new Promise(r => setTimeout(r, ms));
const clone = o => (typeof structuredClone === "function" ? structuredClone(o) : JSON.parse(JSON.stringify(o)));
let fid = 0;
const freshId = () => `sf_mock${(++fid).toString(16).padStart(7, "0")}`;

function fixtureKey(text, resolutions) {
  const keys = Object.keys(resolutions || {});
  if (!keys.length) return text;
  return `${text}|${JSON.stringify(Object.fromEntries(keys.map(k => [String(k), resolutions[k]])))}`;
}

export const mockApi = {
  async health() {
    await wait(60);
    return { ok: true, mode: mockState.mode, mock: true };
  },

  /** POST /api/text-to-sign */
  async textToSign({ text, resolutions = {}, seed = 7, src_lang, sign_lang = "isl" }) {
    if (!text?.trim()) throw new Error("text is empty");
    if (text.length > 500) throw new Error("text too long (500 chars max)");
    await wait(120 + Math.random() * 140);
    const hit = T2S[fixtureKey(text.trim(), resolutions)];
    let res;
    if (hit) {
      res = clone(hit);
      res.plan.frame_id = res.frame.id = freshId();
    } else {
      res = mockTextToSign({ text: text.trim(), resolutions, seed, src_lang, sign_lang });
    }
    const sign = res.plan.targets.find(t => t.kind === "sign");
    if (sign) sign.sign_lang = sign_lang;
    return res;
  },

  /** GET /api/sign/{gloss} */
  async sign(gloss) {
    await wait(40);
    const clip = clipForSign(gloss);
    if (!clip) { const e = new Error(`no sign for ${gloss}`); e.status = 404; throw e; }
    return clip;
  },

  async lexicon() {
    await wait(30);
    return { ...LEXICON, sign_langs: ["isl"] };
  },

  /** GET /api/simcam: one real recorded stream, re-timed; the requested content is remembered for the mock socket */
  async simcam({ text = "", gloss = "", severity = 0, t0 = 0, speed = 1 }) {
    await wait(80);
    const glossList = gloss ? gloss.split(",").map(s => s.trim().toUpperCase()).filter(Boolean) : [];
    const frames = SIMCAM.frames.map(f => {
      const lux = severity > 0.75 ? 10 + 8 * Math.random() : f.lux;
      return { ...f, t: t0 + f.t / speed, lux };
    });
    mockState.queueScenario({ text, gloss: glossList, severity });
    return {
      frames,
      info: { signed: glossList.length ? glossList : (text ? mockTextToSign({ text }).frame.gloss : SIMCAM.info.signed) },
      degrade: { noise: +(0.4 + severity * 3).toFixed(2), dropout: +(severity * 0.5).toFixed(2), lux: severity > 0.75 ? 12 : 140, lefty: false, mirrored: false, speed },
    };
  },

  async evalReport() {
    await wait(60);
    return EVAL;
  },

  async describeScreen(req) {
    await wait(260);
    return { ...describeLocally(req), source: "mock" };
  },

  async userSigns(user) {
    await wait(50);
    return { user, signs: mockState.signs };
  },

  async forgetSign(user, label) {
    await wait(50);
    const before = mockState.signs.length;
    mockState.signs = mockState.signs.filter(s => s.label !== label.toUpperCase());
    return { removed: before - mockState.signs.length };
  },

  async getMode() {
    await wait(30);
    return mockState.modeStatus();
  },

  async setMode(mode) {
    await wait(120);
    return mockState.setMode(mode);
  },
};
