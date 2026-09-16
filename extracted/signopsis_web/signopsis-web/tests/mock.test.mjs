// Contract tests for mock mode: run with `npm test` (bundles src with esbuild first).
import { test } from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const dir = mkdtempSync(join(tmpdir(), "signopsis-"));
const out = join(dir, "bundle.mjs");
await build({
  stdin: {
    contents: `export { mockApi } from "./src/services/mock/mockApi.js";
               export { MockSignSocket } from "./src/services/mock/mockSignSocket.js";
               export { mockState } from "./src/services/mock/mockState.js";
               export { detectLanguage } from "./src/services/speech.js";
               export { trustStateOf, captionFromResult, composeFromResponse } from "./src/services/adapters.js";`,
    resolveDir: process.cwd(), loader: "js",
  },
  bundle: true, format: "esm", platform: "node", outfile: out, logLevel: "error",
});
const M = await import(out);
const sleep = ms => new Promise(r => setTimeout(r, ms));

const GATES = new Set(["emit", "repair", "hold"]);
function checkT2S(res) {
  assert.ok(res.frame && res.plan && res.frames, "response has frame/plan/frames");
  assert.ok(GATES.has(res.plan.gate));
  const sign = res.plan.targets.find(t => t.kind === "sign");
  assert.ok(sign, "sign target");
  assert.ok(res.frames.frames.length > 5);
  for (const f of res.frames.frames) {
    assert.equal(f.Rq.c.length, 5);
    assert.ok(Number.isFinite(f.Rq.x) && Number.isFinite(f.Lq.y));
  }
  return sign;
}

test("fixture sentence returns the recorded backend plan", async () => {
  const r = await M.mockApi.textToSign({ text: "I went to the bank yesterday." });
  const sign = checkT2S(r);
  assert.deepEqual(sign.gloss.map(g => g.g), ["YESTERDAY", "ME", "BANK", "GO"]);
  assert.equal(r.plan.gate, "emit");
});

test("free text goes through the mock resolver with ISL order", async () => {
  const r = await M.mockApi.textToSign({ text: "Tomorrow my friend will not go to school" });
  const sign = checkT2S(r);
  const g = sign.gloss.map(x => x.g);
  assert.equal(g[0], "TOMORROW");
  assert.ok(g.indexOf("NOT") > g.indexOf("GO"), g.join(" "));
});

test("wh-question puts the question word last", async () => {
  const r = await M.mockApi.textToSign({ text: "Where is my book?" });
  const g = checkT2S(r).gloss.map(x => x.g);
  assert.equal(g.at(-1), "WHERE");
  assert.equal(r.frame.question_type, "wh");
});

test("hinglish 'kal' without tense asks, and the answer resolves it", async () => {
  const r = await M.mockApi.textToSign({ text: "kal doctor" });
  assert.equal(r.plan.gate, "repair");
  assert.equal(r.plan.repair.type, "disambiguate");
  const ti = r.plan.repair.token_index;
  const r2 = await M.mockApi.textToSign({ text: "kal doctor", resolutions: { [ti]: "TOMORROW" } });
  assert.equal(r2.plan.gate, "emit");
  assert.ok(r2.frame.gloss.includes("TOMORROW"));
});

test("unknown words are fingerspelled and lower trust", async () => {
  const r = await M.mockApi.textToSign({ text: "Quantum chromodynamics lecture postponed" });
  const sign = checkT2S(r);
  assert.ok(sign.gloss.every(g => g.fingerspelled));
  assert.notEqual(r.plan.gate, "emit");
});

test("recorded fixture repair branches exist", async () => {
  const r = await M.mockApi.textToSign({ text: "mujhe kal bank jaana hai" });
  assert.equal(r.plan.gate, "repair");
  const r2 = await M.mockApi.textToSign({ text: "mujhe kal bank jaana hai", resolutions: { [r.plan.repair.token_index]: "TOMORROW" } });
  assert.equal(r2.frame.gloss[0], "TOMORROW");
});

test("sign clip and 404", async () => {
  const c = await M.mockApi.sign("hello");
  assert.ok(c.frames.length > 10);
  await assert.rejects(() => M.mockApi.sign("NOPE"));
});

test("language detection", () => {
  assert.equal(M.detectLanguage("मुझे पानी चाहिए").code, "hi");
  assert.match(M.detectLanguage("mujhe kal bank jaana hai").code, /^hi/);
  assert.equal(M.detectLanguage("main ghar ja raha hoon").code, "hi");
  assert.equal(M.detectLanguage("I went to the bank yesterday").code, "en");
  assert.equal(M.detectLanguage("வணக்கம் நண்பா").code, "ta");
  assert.equal(M.detectLanguage("hola, dónde está el baño por favor").code, "es");
});

async function playScenario(sock, params) {
  const sim = await M.mockApi.simcam({ ...params, t0: 1000 });
  for (const f of sim.frames) sock.send(f);
  sock.send({ type: "flush" });
  await sleep(20);
}

test("mock socket: clean, ambiguous + repair, teach flow", async () => {
  const sock = new M.MockSignSocket({ user: "t" }).connect();
  const events = [];
  sock.on("*", e => events.push(e));
  await sleep(300);
  assert.equal(events[0].type, "hello");

  await playScenario(sock, { text: "I went to the bank yesterday." });
  let res = events.filter(e => e.type === "result");
  assert.equal(res.at(-1).gate, "emit");
  assert.equal(res.at(-1).text, "Yesterday I went to the bank.");
  assert.ok(events.some(e => e.type === "partial"));
  assert.ok(events.some(e => e.type === "live"));

  await playScenario(sock, { gloss: "ME,RIVER,GO" });
  res = events.filter(e => e.type === "result");
  const amb = res.at(-1);
  assert.equal(amb.gate, "repair");
  const card = M.captionFromResult(amb);
  assert.equal(card.state, "repair");
  sock.send({ type: "repair_choice", frame_id: amb.plan.frame_id, slot: amb.plan.repair.slot, choice: "WATER" });
  await sleep(20);
  const fixed = events.filter(e => e.type === "result").at(-1);
  assert.equal(fixed.gate, "emit");
  assert.match(fixed.text, /water/);
  assert.equal(M.captionFromResult(fixed, { repaired: true }).state, "enhanced");

  await playScenario(sock, { gloss: "MY,NAME,DEMO-NAMESIGN" });
  assert.equal(events.filter(e => e.type === "result").at(-1).gate, "hold", JSON.stringify(events.filter(e => e.type === "result" || e.type === "phrase_start").map(e => e.type + ":" + (e.text ?? e.t))));
  sock.send({ type: "enroll_start", label: "Priya" });
  for (let i = 0; i < 4; i++) await playScenario(sock, { gloss: "DEMO-NAMESIGN" });
  assert.ok(events.some(e => e.type === "enrolled" && e.display === "Priya"));
  await playScenario(sock, { gloss: "MY,NAME,DEMO-NAMESIGN" });
  const known = events.filter(e => e.type === "result").at(-1);
  assert.equal(known.gate, "emit");
  assert.equal(known.text, "My name is Priya.");
  assert.equal(M.trustStateOf(known.gate, { slots: known.slots }), "enhanced");

  await playScenario(sock, { text: "I went to the bank yesterday.", severity: 0.9 });
  assert.equal(events.filter(e => e.type === "result").at(-1).gate, "hold");
  sock.close();
});

test("mode manager mock", async () => {
  const s = await M.mockApi.setMode("CONVERSE");
  assert.equal(s.mode, "CONVERSE");
  assert.ok(s.planned_vram_gb > 0);
  await assert.rejects(() => M.mockApi.setMode("NAP"));
});
