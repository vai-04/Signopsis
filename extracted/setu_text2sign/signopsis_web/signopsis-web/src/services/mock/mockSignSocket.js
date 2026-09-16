// Mock of WS /ws/sign. Speaks the exact same message protocol as the backend's SignSession.
// It does NOT recognise signing: phrase boundaries come from real hand presence in the frames it
// receives (camera or simulator), and the phrase *content* comes from recorded backend transcripts.
import S2T from "../../mocks/s2t.json";
import T2S from "../../mocks/t2s.json";
import { mockState } from "./mockState.js";
import { mockTextToSign } from "./mockResolver.js";

const END_MS = 450;
const clone = o => JSON.parse(JSON.stringify(o));
let n = 0;
const nid = p => `${p}_mock${(++n).toString(16).padStart(8, "0")}`;
const lastResult = name => clone(S2T[name].filter(e => e.type === "result").at(-1));
const CAMERA_ROTATION = ["clean", "question", "ambiguous", "medical", "unknown"];

function withIds(ev) {
  const id = nid("sf");
  ev.plan.frame_id = id;
  if (ev.frame) ev.frame.id = id;
  return ev;
}

function tidy(text) {
  const t = text.trim().replace(/\s+/g, " ");
  if (!t) return t;
  const s = t[0].toUpperCase() + t.slice(1);
  return /[.?!]$/.test(s) ? s : `${s}.`;
}

function synthResult(text, { source = "lattice", display = null } = {}) {
  const ref = T2S[text] || mockTextToSign({ text });
  const gloss = ref.frame.gloss;
  const caption = tidy(display || text);
  const hs = ref.frame.high_stakes;
  const slots = gloss.map((g, i) => ({
    gloss: g, display: g.startsWith("FS:") ? g.slice(3) : g, kind: g.startsWith("FS:") ? "fingerspell" : "sign",
    trust: 0.97, visual_trust: 0.97, source, post: [[g, 0.97]], ctx_margin: 0.9, visual: [[g, 0.97]],
    negated: g === "NOT", t: [120 + i * 560, 520 + i * 560], signals: {},
  }));
  return withIds({
    type: "result", text: caption, draft: caption, gate: "emit", slots,
    percept: { id: nid("pe"), t0: 0, t1: gloss.length * 560, channel: "sign", source: "mock", lang_hint: "isl", lattice: [], nonmanual: null, quality: {}, trust: 0.97, partial: false },
    frame: { ...ref.frame, utterance: caption, lang: "en", trust: 0.97 },
    plan: {
      frame_id: "", gate: "emit", gate_reason: `All ${gloss.length} signs trusted (min 0.97 ≥ ${hs ? 0.85 : 0.75}).`,
      targets: [
        { kind: "caption", lang: "en", text: caption, trust_badge: "high", forced: false, speaker_label: "Signer" },
        { kind: "tts", engine: "browser-speech", lang: "en", text: caption, voice: "default", emphasis: [], rate: 1, pitch: 1, volume: 0.86 },
      ],
      repair: null, advisory: hs ? ref.plan.advisory || "Medical context: confirm important details." : null,
      timings_ms: { decode: 140, resolve: 0.6, total: 142 },
    },
  });
}

export class MockSignSocket {
  constructor({ user = "demo", lang = "en", dominant = "right" } = {}) {
    this.user = user;
    this.cfg = { out_lang: lang, dominant };
    this.listeners = new Map();
    this.status = "idle";
    this.phrase = null;
    this.lastActiveT = null;
    this.frameCount = 0;
    this.enroll = null;
    this.pending = null;
    this.rot = 0;
    this.timers = new Set();
  }

  on(type, fn) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(fn);
    return () => this.listeners.get(type)?.delete(fn);
  }

  _emit(ev) {
    const later = setTimeout(() => {
      this.timers.delete(later);
      if (this.status !== "open" && ev.type !== "status") return;
      this.listeners.get(ev.type)?.forEach(f => f(ev));
      this.listeners.get("*")?.forEach(f => f(ev));
    }, 0);
    this.timers.add(later);
  }

  _setStatus(s) {
    this.status = s;
    this.listeners.get("status")?.forEach(f => f({ type: "status", status: s, mock: true }));
  }

  connect() {
    this._setStatus("connecting");
    const t = setTimeout(() => {
      this._setStatus("open");
      this._emit({ type: "hello", user: this.user, signs: mockState.signs, config: { ...this.cfg }, vocabulary: S2T.clean[0].vocabulary, mock: true });
    }, 250);
    this.timers.add(t);
    return this;
  }

  close() {
    this.timers.forEach(clearTimeout);
    this.timers.clear();
    this._setStatus("closed");
  }

  send(msg) {
    if (this.status !== "open") return false;
    const items = msg.type === "batch" ? msg.items : [msg];
    for (const m of items) this._handle(m);
    return true;
  }

  // ------------------------------------------------------------------ protocol
  _handle(m) {
    switch (m.type) {
      case "frame": return this._frame(m);
      case "flush": return this._endPhrase();
      case "reset": this.phrase = null; this.pending = null; return this._emit({ type: "reset" });
      case "hello": return this._emit({ type: "hello", user: this.user, signs: mockState.signs, config: { ...this.cfg }, vocabulary: S2T.clean[0].vocabulary });
      case "config":
        if (m.out_lang) this.cfg.out_lang = m.out_lang;
        if (m.dominant) this.cfg.dominant = m.dominant;
        return this._emit({ type: "config", ...this.cfg });
      case "list_signs": return this._emit({ type: "signs", signs: mockState.signs });
      case "forget_sign": {
        const before = mockState.signs.length;
        mockState.signs = mockState.signs.filter(s => s.label !== String(m.label).toUpperCase());
        return this._emit({ type: "signs", signs: mockState.signs, removed: before - mockState.signs.length });
      }
      case "enroll_start":
      case "enroll_from_unknown": {
        const label = String(m.label || "").trim();
        if (!label) return this._emit({ type: "error", message: "a sign needs a name" });
        const have = m.type === "enroll_from_unknown" ? 1 : 0;
        this.enroll = { label: label.toUpperCase().replace(/\s+/g, "-"), display: label, have };
        return this._emit({ type: "enroll_progress", label: this.enroll.label, display: label, have, need: 4 });
      }
      case "enroll_cancel":
        this.enroll = null;
        return this._emit({ type: "enroll_progress", label: null, have: 0, need: 4, cancelled: true });
      case "enroll_undo": {
        const e = this.enroll;
        if (!e) return this._emit({ type: "error", message: "not enrolling" });
        e.have = Math.max(0, e.have - 1);
        return this._emit({ type: "enroll_progress", label: e.label, display: e.display, have: e.have, need: 4, undone: true });
      }
      case "repair_choice": return this._repair(m);
      default: return this._emit({ type: "error", message: `unknown message type '${m.type}'` });
    }
  }

  _frame(f) {
    this.frameCount++;
    const active = (f.hands || []).length > 0;
    const hint = f.lux != null && f.lux < 40 ? "Too dark" : !f.pose ? "Move back so your shoulders are visible" : null;
    if (active) {
      this.lastActiveT = f.t;
      if (!this.phrase) {
        const scenario = this._pickScenario();            // always consume, even while enrolling
        this.phrase = { t0: f.t, frames: 0, scenario: this.enroll ? null : scenario };
        this._emit({ type: "phrase_start", t: f.t, enrolling: !!this.enroll });
      }
    } else if (this.phrase && this.lastActiveT != null && f.t - this.lastActiveT > END_MS) {
      this._endPhrase();
    }
    if (this.phrase) {
      this.phrase.frames++;
      const g = this.phrase.scenario?.gloss || [];
      if (!this.enroll && g.length && this.phrase.frames % 22 === 0) {
        const k = Math.min(g.length, Math.ceil(this.phrase.frames / 22));
        this._emit({ type: "partial", gloss: g.slice(0, k), t: f.t });
      }
    }
    if (this.frameCount % 6 === 0) {
      this._emit({
        type: "live", t: f.t, signing: !!this.phrase, enrolling: !!this.enroll,
        hands: { R: (f.hands || []).some(h => /left/i.test(h.label)), L: (f.hands || []).some(h => /right/i.test(h.label)) },
        anchor: !!f.pose, lux: f.lux ?? null, hint: this.phrase && !active ? "Hands out of view" : hint,
        brow: (f.face?.bs?.browInnerUp || 0) > 0.45 ? "raised" : (f.face?.bs?.browDownLeft || 0) > 0.45 ? "furrowed" : "neutral",
      });
    }
  }

  _pickScenario() {
    const q = mockState.nextScenario();
    let name;
    if (q) {
      const g = q.gloss?.length ? q.gloss : (T2S[q.text] || mockTextToSign({ text: q.text })).frame.gloss;
      const same = ["clean", "question", "medical"].find(k => lastResult(k).slots.map(s => s.gloss).join() === g.join());
      if (q.severity > 0.75) name = "dark";
      else if (same) name = same;
      else if (g.includes("RIVER") || g.includes("WATER")) name = "ambiguous";
      else if (g.some(x => x.startsWith("DEMO-"))) name = "unknown";
      else if (q.gloss?.length) return { kind: "text", text: g.map(x => x.toLowerCase()).join(" "), gloss: g };
      else return { kind: "text", text: q.text, gloss: g };
    } else {
      name = CAMERA_ROTATION[this.rot++ % CAMERA_ROTATION.length];
    }
    const res = lastResult(name);
    return { kind: "fixture", name, gloss: res.slots.map(s => s.gloss) };
  }

  _endPhrase() {
    const p = this.phrase;
    this.phrase = null;
    this.lastActiveT = null;
    if (!p) return;
    if (this.enroll) return this._enrollSample(p);
    const sc = p.scenario;
    let ev;
    if (sc.kind === "text") ev = synthResult(sc.text);
    else if (sc.name === "unknown" && mockState.signs.length) {
      const mine = mockState.signs[0];
      ev = synthResult("My name is " + mine.display, { source: "user" });
      ev.slots[2] = { ...ev.slots[2], gloss: mine.label, display: mine.display, kind: "sign", source: "user" };
    } else ev = withIds(lastResult(sc.name));
    if (ev.plan.repair) this.pending = { ev, scenario: sc };
    this._emit(ev);
    if (sc.name === "unknown" && !mockState.signs.length) {
      this.unknownSeen = (this.unknownSeen || 0) + 1;
      if (this.unknownSeen === 2) this._emit({ type: "teach_offer", samples: 2, need: 4, prompt: "You've used a sign I don't know twice. Teach it to me?" });
    }
  }

  _enrollSample(p) {
    const e = this.enroll;
    if (p.frames < 5) {
      return this._emit({ type: "enroll_progress", label: e.label, display: e.display, have: e.have, need: 4, warning: "That was too short. Please sign it again." });
    }
    e.have++;
    if (e.have < 4) return this._emit({ type: "enroll_progress", label: e.label, display: e.display, have: e.have, need: 4 });
    this.enroll = null;
    mockState.signs = [...mockState.signs.filter(s => s.label !== e.label), { label: e.label, display: e.display, samples: 4, created: Date.now() / 1000 }];
    this._emit({ type: "enrolled", label: e.label, display: e.display, prototypes: 5, consistency: 0.31, warning: null });
    this._emit({ type: "signs", signs: mockState.signs });
  }

  _repair(m) {
    const pend = this.pending;
    if (!pend || (m.frame_id && m.frame_id !== pend.ev.plan.frame_id)) {
      return this._emit({ type: "error", message: "nothing to repair (the phrase has expired)" });
    }
    const choice = m.choice;
    if (choice === "__none__") {
      this.pending = null;
      return this._emit({ type: "repair_done", frame_id: pend.ev.plan.frame_id, outcome: "dismissed" });
    }
    if (choice === "__teach__") {
      return this._emit({ type: "teach_offer", samples: 1, need: 4, prompt: "What does this sign mean?" });
    }
    this.pending = null;
    if (pend.scenario.name === "ambiguous") {
      const ev = withIds(clone(S2T.ambiguous_after_RIVER[0]));
      if (choice !== "RIVER" && choice !== "__accept__") {
        const word = String(choice).toLowerCase();
        ev.text = ev.draft = ev.text.replace("river", word);
        ev.plan.targets.forEach(t => { if (t.text) t.text = t.text.replace("river", word); });
        ev.slots = ev.slots.map(s => (s.gloss === "RIVER" ? { ...s, gloss: choice, display: choice } : s));
        if (ev.frame) ev.frame.gloss = ev.frame.gloss.map(g => (g === "RIVER" ? choice : g));
      }
      ev.slots = ev.slots.map((s, i) => (i === m.slot ? { ...s, source: "user" } : s));
      return this._emit(ev);
    }
    const ev = clone(pend.ev);
    ev.gate = "emit"; ev.text = ev.draft || ev.text; ev.plan.gate = "emit"; ev.plan.repair = null;
    ev.plan.gate_reason = "Accepted by you.";
    return this._emit(withIds(ev));
  }
}
