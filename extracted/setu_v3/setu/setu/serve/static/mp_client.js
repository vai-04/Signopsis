// SETU camera client: webcam -> MediaPipe (in the browser) -> wire frames.
// Raw video never leaves this page. Only landmarks, a few face blendshapes and
// one brightness number are sent (design rule 5).
//
// Load order for MediaPipe: local vendor copy (python scripts/fetch_models.py),
// then the public CDN / model bucket.

const TV_VERSION = "1.0.1";
const LOCAL_TV = "/static/vendor/tasks-vision";
const CDN_TV = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${TV_VERSION}`;
const MODELS = {
  hand: ["/static/vendor/models/hand_landmarker.task",
         "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"],
  pose: ["/static/vendor/models/pose_landmarker_lite.task",
         "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"],
  face: ["/static/vendor/models/face_landmarker.task",
         "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"],
};
const BLEND_KEYS = ["browInnerUp", "browOuterUpLeft", "browOuterUpRight", "browDownLeft", "browDownRight",
                    "cheekPuff", "jawOpen", "mouthPucker"];

async function exists(url) {
  try { const r = await fetch(url, { method: "HEAD" }); return r.ok; } catch { return false; }
}

async function firstAvailable(urls) {
  for (const u of urls.slice(0, -1)) if (await exists(u)) return u;
  return urls[urls.length - 1];
}

export async function loadVision(log = () => {}) {
  let mod, base;
  if (await exists(`${LOCAL_TV}/vision_bundle.mjs`)) {
    mod = await import(`${LOCAL_TV}/vision_bundle.mjs`);
    base = (await exists(`${LOCAL_TV}/wasm/vision_wasm_internal.wasm`)) ? `${LOCAL_TV}/wasm` : `${CDN_TV}/wasm`;
    log(`MediaPipe JS: local · wasm: ${base.startsWith("/") ? "local" : "CDN"}`);
  } else {
    mod = await import(`${CDN_TV}/vision_bundle.mjs`);
    base = `${CDN_TV}/wasm`;
    log("MediaPipe JS: CDN");
  }
  const fileset = await mod.FilesetResolver.forVisionTasks(base);
  return { mod, fileset };
}

async function create(Task, fileset, url, opts, log, name) {
  for (const delegate of ["GPU", "CPU"]) {
    try {
      return await Task.createFromOptions(fileset, { baseOptions: { modelAssetPath: url, delegate }, runningMode: "VIDEO", ...opts });
    } catch (e) {
      log(`${name} model on ${delegate} failed: ${e.message || e}`);
    }
  }
  throw new Error(`could not load ${url}`);
}

export class CameraSource {
  constructor({ video, onFrame, onLandmarks, log = () => {}, faceEvery = 2 }) {
    Object.assign(this, { video, onFrame, onLandmarks, log, faceEvery });
    this.running = false;
    this.n = 0;
    this.lastFace = null;
    this.lux = null;
    this.tiny = document.createElement("canvas");
    this.tiny.width = 16; this.tiny.height = 12;
    this.fps = 0;
  }

  async init() {
    const { mod, fileset } = await loadVision(this.log);
    const [hand, pose, face] = await Promise.all([firstAvailable(MODELS.hand), firstAvailable(MODELS.pose), firstAvailable(MODELS.face)]);
    this.log(`models: ${[hand, pose, face].every(u => u.startsWith("/")) ? "local" : "remote"}`);
    this.hands = await create(mod.HandLandmarker, fileset, hand, { numHands: 2, minHandDetectionConfidence: 0.5, minTrackingConfidence: 0.5 }, this.log, "hand");
    this.pose = await create(mod.PoseLandmarker, fileset, pose, { numPoses: 1 }, this.log, "pose");
    try {
      this.face = await create(mod.FaceLandmarker, fileset, face, { numFaces: 1, outputFaceBlendshapes: true }, this.log, "face");
    } catch (e) {
      this.face = null;
      this.log("face model unavailable: non-manual markers disabled");
    }
  }

  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 30 } }, audio: false });
    this.video.srcObject = this.stream;
    await this.video.play();
    if (!this.hands) await this.init();
    this.running = true;
    this.lastT = performance.now();
    this._loop();
  }

  stop() {
    this.running = false;
    if (this.stream) this.stream.getTracks().forEach(t => t.stop());
    this.stream = null;
  }

  _schedule() {
    if (!this.running) return;
    if (this.video.requestVideoFrameCallback) this.video.requestVideoFrameCallback(() => this._loop());
    else requestAnimationFrame(() => this._loop());
  }

  _brightness() {
    const c = this.tiny.getContext("2d", { willReadFrequently: true });
    c.drawImage(this.video, 0, 0, 16, 12);
    const d = c.getImageData(0, 0, 16, 12).data;
    let s = 0;
    for (let i = 0; i < d.length; i += 4) s += 0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2];
    return s / (d.length / 4);
  }

  _loop() {
    if (!this.running) return;
    const v = this.video;
    if (v.readyState < 2 || !v.videoWidth) return this._schedule();
    const ts = Math.max(performance.now(), (this.lastTs || 0) + 1);   // MediaPipe needs strictly increasing time
    this.lastTs = ts;
    this.n++;
    let hr, pr;
    try {
      hr = this.hands.detectForVideo(v, ts);
      pr = this.pose.detectForVideo(v, ts);
      if (this.face && this.n % this.faceEvery === 0) this.lastFace = this.face.detectForVideo(v, ts);
      if (this.n % 10 === 1) this.lux = this._brightness();
    } catch (e) {
      if (this.n % 30 === 1) this.log("detector error: " + (e.message || e));
      return this._schedule();
    }

    const hands = (hr.landmarks || []).map((lm, i) => ({
      lm: lm.map(p => [p.x, p.y, p.z]),
      label: ((hr.handedness || hr.handednesses || [])[i] || [{}])[0].categoryName || "",
      score: ((hr.handedness || hr.handednesses || [])[i] || [{}])[0].score ?? 1,
    }));
    const poseLm = pr.landmarks && pr.landmarks[0] ? pr.landmarks[0].slice(0, 25).map(p => [p.x, p.y, p.z, p.visibility ?? 1]) : null;
    let face = null;
    const fr = this.lastFace;
    if (fr && fr.faceLandmarks && fr.faceLandmarks[0]) {
      const bs = {};
      const cats = fr.faceBlendshapes && fr.faceBlendshapes[0] ? fr.faceBlendshapes[0].categories : [];
      for (const c of cats) if (BLEND_KEYS.includes(c.categoryName)) bs[c.categoryName] = +c.score.toFixed(3);
      const nose = fr.faceLandmarks[0][1];
      face = { bs, nose: [nose.x, nose.y] };
    }
    const frame = { type: "frame", t: +ts.toFixed(1), w: v.videoWidth, h: v.videoHeight,
                    hands, pose: poseLm, face, lux: this.lux, mirrored: false };
    const dt = ts - this.lastT; this.lastT = ts;
    this.fps = 0.9 * this.fps + 0.1 * (1000 / Math.max(dt, 1));
    this.onLandmarks && this.onLandmarks(frame);
    this.onFrame && this.onFrame(frame);
    this._schedule();
  }
}

// Draw a wire frame's landmarks on a canvas (image-normalised coordinates).
const HAND_EDGES = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],
                    [9,13],[13,14],[14,15],[15,16],[13,17],[17,18],[18,19],[19,20],[0,17]];
const POSE_EDGES = [[11,12],[11,13],[13,15],[12,14],[14,16],[11,23],[12,24],[23,24]];

export function drawLandmarks(ctx, frame, { clear = true, background = null } = {}) {
  const W = ctx.canvas.width, H = ctx.canvas.height;
  if (clear) ctx.clearRect(0, 0, W, H);
  if (background) { ctx.fillStyle = background; ctx.fillRect(0, 0, W, H); }
  const X = p => (frame.mirrored ? 1 - p[0] : p[0]) * W, Y = p => p[1] * H;
  ctx.lineWidth = Math.max(2, W / 320);
  if (frame.pose) {
    ctx.strokeStyle = "rgba(160,200,255,.8)";
    for (const [a, b] of POSE_EDGES) {
      const p = frame.pose[a], q = frame.pose[b];
      if (!p || !q || (p[3] ?? 1) < .4 || (q[3] ?? 1) < .4) continue;
      ctx.beginPath(); ctx.moveTo(X(p), Y(p)); ctx.lineTo(X(q), Y(q)); ctx.stroke();
    }
    const n = frame.pose[0];
    if (n && (n[3] ?? 1) > .4) { ctx.fillStyle = "rgba(160,200,255,.9)"; ctx.beginPath(); ctx.arc(X(n), Y(n), W / 90, 0, 7); ctx.fill(); }
  }
  frame.hands.forEach((h, i) => {
    const right = /left/i.test(h.label) !== !!frame.mirrored;    // person's right hand
    ctx.strokeStyle = right ? "#ffb35c" : "#6fe3c1";
    ctx.fillStyle = ctx.strokeStyle;
    for (const [a, b] of HAND_EDGES) {
      ctx.beginPath(); ctx.moveTo(X(h.lm[a]), Y(h.lm[a])); ctx.lineTo(X(h.lm[b]), Y(h.lm[b])); ctx.stroke();
    }
    for (const p of h.lm) { ctx.beginPath(); ctx.arc(X(p), Y(p), W / 200 + 1, 0, 7); ctx.fill(); }
  });
  if (frame.face && frame.face.nose) {
    ctx.fillStyle = "#ff7ab6";
    ctx.beginPath(); ctx.arc(X(frame.face.nose), Y(frame.face.nose), W / 120, 0, 7); ctx.fill();
  }
}
