// SIGNOPSIS 3D signer page logic: text -> sign playback, mirror-me (webcam retargeting), pose lab, styling.
import * as THREE from "../lib/three-bundle.min.js";
import { createAvatar, addLights, makeBackground, PALETTE } from "./avatar.js";
import { lerpParams, REST, retargetFrame } from "./rig.js";

const $ = id => document.getElementById(id);
const status = m => { $("status").textContent = m; };
const DEMO = window.SIGNOPSIS_AVATAR_DEMO || null;       // offline build embeds precomputed plans

/* ------------------------------------------------------------ scene */
const canvas = $("stage");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 1.75));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
const scene = new THREE.Scene();
addLights(scene);
const camera = new THREE.PerspectiveCamera(28, 1, 0.05, 50);
const controls = new THREE.OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.minDistance = 0.4; controls.maxDistance = 6;
const avatar = createAvatar();
scene.add(avatar.group);

const VIEWS = {
  front: { pos: [0, 1.46, 2.25], tgt: [0, 1.36, 0] },
  three: { pos: [1.25, 1.55, 1.9], tgt: [0, 1.36, 0] },
  hands: { pos: [0.15, 1.38, 1.25], tgt: [0, 1.32, 0.2] },
  side: { pos: [2.2, 1.5, 0.4], tgt: [0, 1.36, 0.1] },
  full: { pos: [0, 1.0, 3.6], tgt: [0, 0.94, 0] },
};
let viewAnim = null;
let currentView = "front";
function setView(name, instant = false) {
  currentView = name;
  const base = VIEWS[name];
  // portrait screens need the camera further back to fit the same shot
  const k = camera.aspect < 0.8 ? 1.75 : 1;
  const tg = new THREE.Vector3(...base.tgt);
  const ps = new THREE.Vector3(...base.pos).sub(tg).multiplyScalar(k).add(tg);
  const v = { pos: ps.toArray(), tgt: base.tgt };
  document.querySelectorAll("#views [data-view]").forEach(b => b.classList.toggle("on", b.dataset.view === name));
  if (instant) { camera.position.set(...v.pos); controls.target.set(...v.tgt); controls.update(); return; }
  viewAnim = { t: 0, p0: camera.position.clone(), q0: controls.target.clone(), p1: new THREE.Vector3(...v.pos), q1: new THREE.Vector3(...v.tgt) };
}
document.querySelectorAll("#views [data-view]").forEach(b => b.onclick = () => setView(b.dataset.view));
$("spin").onclick = () => { controls.autoRotate = !controls.autoRotate; $("spin").classList.toggle("on", controls.autoRotate); };
function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (!w || !h) return;
  const wasPortrait = camera.aspect < 0.8;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  if (wasPortrait !== (camera.aspect < 0.8)) setView(currentView, true);
}
new ResizeObserver(resize).observe(canvas);
resize();
setView("front", true);

let bgKind = "green";
function setBackground(kind) {
  bgKind = kind;
  scene.background = makeBackground(kind);
  $("stageWrap").style.background = kind === "transparent" ? "repeating-conic-gradient(#ddd 0 25%, #fff 0 50%) 0 0/20px 20px" : "#43c22e";
}
setBackground("green");

/* ------------------------------------------------------------ playback state */
const player = { frames: null, fps: 30, total: 0, t: 0, playing: false, gloss: [], plan: null };
let mode = "text";            // text | mirror | lab
let liveFrame = null;         // for mirror / lab modes
let clickWave = null;

function frameAt(ms) {
  const F = player.frames;
  if (!F || !F.length) return null;
  const x = ms / (1000 / player.fps);
  const i = Math.max(0, Math.min(F.length - 1, Math.floor(x)));
  const j = Math.min(F.length - 1, i + 1);
  const a = F[i], b = F[j], u = Math.min(1, Math.max(0, x - i));
  return { Rq: lerpParams(a.Rq, b.Rq, u), Lq: lerpParams(a.Lq, b.Lq, u), face: u < 0.5 ? a.face : b.face, gi: a.gi, ch: a.ch };
}

function setPlaying(on) {
  player.playing = on;
  $("play").textContent = on ? "❚❚ Pause" : "▶ Play";
  avatar.setSigning(on);
}
$("play").onclick = () => { if (!player.frames) return; if (player.t >= player.total) player.t = 0; setPlaying(!player.playing); };
$("replay").onclick = () => { player.t = 0; setPlaying(true); };
$("scrub").oninput = e => { setPlaying(false); player.t = (+e.target.value / 1000) * player.total; };
$("skel").onchange = e => avatar.setSkeleton(e.target.checked);
$("expr").onchange = e => avatar.setExpression(e.target.value);
$("snap").onclick = () => {
  const a = document.createElement("a");
  a.download = "signopsis-avatar.png"; a.href = canvas.toDataURL("image/png"); a.click();
};

/* ------------------------------------------------------------ text -> sign */
const EXAMPLES = ["Hello, my name is Priya. What is your name?", "I went to the bank yesterday.", "Do you want water?",
  "I don't understand.", "Thank you! See you tomorrow.", "Where is the hospital?", "mujhe kal bank jaana hai", "main kal ghar gaya tha"];
for (const ex of EXAMPLES) {
  const c = document.createElement("span"); c.className = "chip"; c.textContent = ex;
  c.onclick = () => { $("text").value = ex; signText(); };
  $("examples").appendChild(c);
}

let reqId = 0;
async function fetchPlan(text, resolutions) {
  if (DEMO) {
    const key = Object.keys(resolutions || {}).length ? text + "|" + JSON.stringify(resolutions) : text;
    if (DEMO.results[key]) return DEMO.results[key];
    throw new Error("The offline demo only has the example sentences. Run the SIGNOPSIS server for free text.");
  }
  const r = await fetch("/api/text-to-sign", { method: "POST", headers: { "Content-Type": "application/json" },
                                               body: JSON.stringify({ text, resolutions: resolutions || {} }) });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function signText(resolutions) {
  const text = $("text").value.trim();
  if (!text) return;
  const my = ++reqId;
  status("translating…");
  try {
    const t0 = performance.now();
    const res = await fetchPlan(text, resolutions);
    if (my !== reqId) return;                          // a newer request superseded this one
    loadPlan(res, text);
    status(`ready in ${Math.round(performance.now() - t0)} ms`);
  } catch (e) { status(""); $("gloss").innerHTML = `<span class="err">${e.message}</span>`; }
}

function loadPlan(res, text) {
  const plan = res.plan, sign = plan.targets.find(t => t.kind === "sign");
  player.frames = res.frames.frames; player.fps = res.frames.fps; player.total = res.frames.total_ms;
  player.gloss = sign.gloss; player.plan = plan; player.text = text; player.t = 0;
  switchMode("text");
  // gate + repair
  const trust = res.frame.trust;
  $("gate").innerHTML = `<span class="pill ${plan.gate}">${plan.gate}</span><span class="muted">trust ${trust.toFixed(2)} · read-back ${sign.roundtrip_score.toFixed(2)}</span>`;
  $("gloss").textContent = sign.back_translation ? `Reads back as: ${sign.back_translation}` : "";
  const rep = $("repair"); rep.innerHTML = "";
  if (plan.repair && plan.repair.type === "disambiguate") {
    const p = document.createElement("div"); p.className = "muted"; p.textContent = plan.repair.prompt; rep.appendChild(p);
    const row = document.createElement("div"); row.className = "row"; row.style.marginTop = "6px";
    for (const o of plan.repair.options) {
      const b = document.createElement("button"); b.className = "primary"; b.textContent = o.label;
      b.onclick = () => signText({ [plan.repair.token_index]: o.gloss });
      row.appendChild(b);
    }
    rep.appendChild(row);
  } else if (plan.gate !== "emit") {
    rep.innerHTML = `<span class="muted">${plan.gate_reason}</span>`;
  }
  // strip
  const strip = $("strip"); strip.innerHTML = "";
  sign.gloss.forEach((g, k) => {
    const el = document.createElement("div"); el.className = "g";
    const label = g.fingerspelled ? (g.fs_fallback || g.g) : g.g;
    el.innerHTML = `${label}<small>${g.fingerspelled ? "spelled" : "sign"} · ${Math.round((g.roundtrip ?? 0) * 100)}%</small>`;
    el.onclick = () => { const F = player.frames; const j = F.findIndex(f => f.gi === k); if (j >= 0) { player.t = j * 1000 / player.fps; setPlaying(true); } };
    strip.appendChild(el);
  });
  // never auto-play something the gate didn't clear
  setPlaying(plan.gate === "emit");
  if (plan.gate !== "emit") avatar.setSigning(false);
}

$("go").onclick = () => signText();
let typeTimer = null;
$("text").addEventListener("input", () => { if (!$("live").checked) return; clearTimeout(typeTimer); typeTimer = setTimeout(() => signText(), 650); });
$("text").addEventListener("keydown", e => { if (e.key === "Enter") signText(); });

// click the avatar -> it waves hello
const ray = new THREE.Raycaster();
canvas.addEventListener("click", async e => {
  if (mode !== "text") return;
  const r = canvas.getBoundingClientRect();
  ray.setFromCamera({ x: ((e.clientX - r.left) / r.width) * 2 - 1, y: -((e.clientY - r.top) / r.height) * 2 + 1 }, camera);
  if (!ray.intersectObjects(avatar.pickables, false).length) return;
  if (player.playing) return;
  try { const res = await fetchPlan("Hello"); loadPlan(res, "Hello!"); } catch {}
});

/* ------------------------------------------------------------ modes */
function switchMode(m) {
  mode = m;
  $("tabText").classList.toggle("on", m === "text"); $("tabMirror").classList.toggle("on", m === "mirror"); $("tabLab").classList.toggle("on", m === "lab");
  $("panelText").hidden = m !== "text"; $("panelMirror").hidden = m !== "mirror"; $("panelLab").hidden = m !== "lab";
  if (m !== "text") setPlaying(false);
  if (m !== "mirror") stopCamera();
  if (m === "lab") { liveFrame = labFrame(); avatar.setSigning(true); setView("hands"); }
  if (m === "mirror") { liveFrame = null; avatar.setSigning(true); }
  $("nowGloss").textContent = ""; $("nowLetter").textContent = ""; $("subtitle").innerHTML = "";
}
$("tabText").onclick = () => switchMode("text");
$("tabMirror").onclick = () => switchMode("mirror");
$("tabLab").onclick = () => switchMode("lab");

/* ------------------------------------------------------------ mirror me */
let cam = null, smooth = null, simTimer = null;
function smoothFrame(target, k = 0.45) {
  if (!smooth) { smooth = JSON.parse(JSON.stringify(target)); return smooth; }
  for (const s of ["Rq", "Lq"]) if (target[s]) smooth[s] = lerpParams(smooth[s] || target[s], target[s], k);
  smooth.face = target.face;
  return smooth;
}
function onWire(frame) {
  const tgt = retargetFrame(frame, { mirror: $("mirrorMode").checked, prev: smooth });
  // hands that disappear drift back to rest instead of freezing
  for (const s of ["R", "L"]) if (!tgt.seen[s]) tgt[s + "q"] = lerpParams(tgt[s + "q"] || REST[s], REST[s], 0.08);
  liveFrame = smoothFrame(tgt);
  $("mirrorInfo").textContent = `hands: ${tgt.seen.R ? "R" : "-"} ${tgt.seen.L ? "L" : "-"} · brows ${tgt.face.brow} · mouth ${tgt.face.mouth}`;
}
async function startCamera() {
  $("camBtn").disabled = true;
  $("mirrorInfo").textContent = "Loading MediaPipe…";
  try {
    const { CameraSource } = await import(/* @vite-ignore */ new URL("../mp_client.js", import.meta.url).href);
    cam = cam || new CameraSource({ video: $("pip"), onFrame: onWire, log: m => { $("mirrorInfo").textContent = m; } });
    await cam.start();
    $("pip").hidden = !$("pipOn").checked;
    $("camBtn").textContent = "Stop camera";
  } catch (e) {
    $("mirrorInfo").innerHTML = `<span class="err">Camera or MediaPipe failed: ${e.message || e}</span>`;
  } finally { $("camBtn").disabled = false; }
}
function stopCamera() {
  if (cam && cam.running) cam.stop();
  clearTimeout(simTimer);
  $("pip").hidden = true;
  $("camBtn").textContent = "Start camera";
}
$("camBtn").onclick = () => (cam && cam.running) ? stopCamera() : startCamera();
$("pipOn").onchange = () => { $("pip").hidden = !($("pipOn").checked && cam && cam.running); };
$("simMirror").onclick = async () => {
  stopCamera();
  const r = await fetch(`/api/simcam?text=${encodeURIComponent("Hello, I don't understand. Where is the hospital?")}&seed=1`);
  if (!r.ok) { $("mirrorInfo").textContent = "Simulator needs the SIGNOPSIS server."; return; }
  const { frames } = await r.json();
  const start = performance.now(), base = frames[0].t; let i = 0;
  const tick = () => {
    const now = performance.now() - start;
    while (i < frames.length && frames[i].t - base <= now) onWire(frames[i++]);
    if (i < frames.length) simTimer = setTimeout(tick, 15);
  };
  tick();
};

/* ------------------------------------------------------------ pose lab */
const SHAPES = {
  flat: [0, 0, 0, 0, 0, 0], open: [0, 0, 0, 0, 0, 1], fist: [0.55, 1, 1, 1, 1, 0], point: [1, 0, 1, 1, 1, 0],
  V: [1, 0, 0, 1, 1, 1], Y: [0, 1, 1, 1, 0, 1], L: [0, 0, 1, 1, 1, 1], C: [0.3, 0.5, 0.5, 0.5, 0.5, 0],
  O: [0.75, 0.78, 0.78, 0.78, 0.78, 0], thumb: [0, 1, 1, 1, 1, 0], W: [1, 0, 0, 0, 1, 1], I: [1, 1, 1, 1, 0, 0],
};
const LAB = [["thumb", 0, 1, 0.01], ["index", 0, 1, 0.01], ["middle", 0, 1, 0.01], ["ring", 0, 1, 0.01], ["pinky", 0, 1, 0.01],
             ["spread", 0, 1, 0.01], ["x", 10, 70, 0.5], ["y", 10, 85, 0.5], ["rotate", -180, 180, 1], ["palm", -1, 1, 0.05]];
const labVals = { thumb: 0, index: 0, middle: 0, ring: 0, pinky: 0, spread: 0, x: 40, y: 50, rotate: 0, palm: 1 };
const labDefaults = { ...labVals };
for (const [k, lo, hi, st] of LAB) {
  const lab = document.createElement("label"); lab.textContent = k; lab.htmlFor = "lab_" + k;
  const inp = document.createElement("input"); inp.type = "range"; inp.min = lo; inp.max = hi; inp.step = st; inp.id = "lab_" + k; inp.value = labVals[k];
  const out = document.createElement("output"); out.textContent = labVals[k];
  inp.oninput = () => { labVals[k] = +inp.value; out.textContent = inp.value; liveFrame = labFrame(); };
  $("sliders").append(lab, inp, out);
}
function syncLab() { for (const [k] of LAB) { $("lab_" + k).value = labVals[k]; $("lab_" + k).nextSibling.textContent = labVals[k]; } liveFrame = labFrame(); }
function labFrame() {
  return { Rq: { c: [labVals.thumb, labVals.index, labVals.middle, labVals.ring, labVals.pinky], s: labVals.spread,
                 x: labVals.x, y: labVals.y, r: labVals.rotate, p: labVals.palm }, Lq: REST.L, face: { brow: "neutral", head: "neutral", mouth: "neutral", hx: 0, hy: 0 } };
}
for (const [name, v] of Object.entries(SHAPES)) {
  const c = document.createElement("span"); c.className = "chip"; c.textContent = name;
  c.onclick = () => { [labVals.thumb, labVals.index, labVals.middle, labVals.ring, labVals.pinky, labVals.spread] = v; syncLab(); };
  $("shapes").appendChild(c);
}
$("labReset").onclick = () => { Object.assign(labVals, labDefaults); syncLab(); };
$("labCopy").onclick = () => navigator.clipboard?.writeText(JSON.stringify(labFrame().Rq));

/* ------------------------------------------------------------ look */
function swatches(id, entries, onPick, current) {
  const box = $(id);
  for (const [name, col] of entries) {
    const b = document.createElement("button"); b.className = "sw" + (name === current ? " on" : "");
    b.style.background = col; b.title = name; b.setAttribute("aria-label", name);
    b.onclick = () => { box.querySelectorAll(".sw").forEach(x => x.classList.remove("on")); b.classList.add("on"); onPick(col, name); };
    box.appendChild(b);
  }
}
swatches("swSkin", Object.entries(PALETTE.skin), c => avatar.setColors({ skin: c }), "warm");
swatches("swHair", Object.entries(PALETTE.hair), c => avatar.setColors({ hair: c }), "black");
swatches("swHoodie", Object.entries(PALETTE.hoodie), c => avatar.setColors({ hoodie: c }), "black");
swatches("swJeans", Object.entries(PALETTE.jeans), c => avatar.setColors({ jeans: c }), "light");
swatches("swBg", [["green", "#43c22e"], ["studio", "#dcd8cf"], ["sky", "#8cc7f2"], ["night", "#1b2230"], ["transparent", "conic-gradient(#ccc 0 25%,#fff 0 50%,#ccc 0 75%,#fff 0)"]],
         (c, n) => setBackground(n), "green");

/* ------------------------------------------------------------ loop */
const clock = { last: performance.now(), elapsedTime: 0,
  getDelta() { const n = performance.now(), d = (n - this.last) / 1000; this.last = n; this.elapsedTime += d; return d; } };
let fpsAcc = 0, fpsN = 0;
function tick() {
  const dt = Math.min(clock.getDelta(), 0.1);
  const t = clock.elapsedTime;
  fpsAcc += dt; fpsN++;
  if (fpsAcc > 0.5) { $("fps").textContent = `${Math.round(fpsN / fpsAcc)} fps`; fpsAcc = 0; fpsN = 0; }
  if (viewAnim) {
    viewAnim.t = Math.min(1, viewAnim.t + dt * 2.2);
    const e = viewAnim.t * viewAnim.t * (3 - 2 * viewAnim.t);
    camera.position.lerpVectors(viewAnim.p0, viewAnim.p1, e);
    controls.target.lerpVectors(viewAnim.q0, viewAnim.q1, e);
    if (viewAnim.t >= 1) viewAnim = null;
  }
  let frame = null;
  if (mode === "text" && player.frames) {
    if (player.playing) {
      player.t += dt * 1000 * +$("speed").value;
      if (player.t >= player.total) {
        if ($("loop").checked) player.t = 0; else { player.t = player.total; setPlaying(false); }
      }
    }
    frame = frameAt(player.t);
    $("scrub").value = Math.round((player.t / (player.total || 1)) * 1000);
    const g = frame && frame.gi >= 0 ? player.gloss[frame.gi] : null;
    $("nowGloss").textContent = g ? (g.fingerspelled ? "fingerspelling" : g.g) : "";
    $("nowLetter").textContent = frame && frame.ch ? frame.ch : "";
    $("subtitle").innerHTML = player.plan && player.plan.gate === "emit" && player.t > 0 && player.t < player.total ? `<span></span>` : "";
    if ($("subtitle").firstChild) $("subtitle").firstChild.textContent = player.text;
    document.querySelectorAll("#strip .g").forEach((el, k) => el.classList.toggle("on", !!frame && frame.gi === k));
  } else if (mode !== "text") {
    frame = liveFrame;
  }
  avatar.update(frame, t, dt);
  controls.update();
  renderer.render(scene, camera);
  requestAnimationFrame(tick);
}
status(DEMO ? "offline demo" : "connected to SIGNOPSIS");
requestAnimationFrame(tick);
window.__signopsis = { avatar, player, camera, controls, setView, loadPlan, signText, switchMode, labVals, syncLab };
signText();
