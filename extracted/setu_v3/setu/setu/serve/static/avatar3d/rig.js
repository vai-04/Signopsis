// SETU 3D avatar rig: pure math, no rendering (so it runs in Node tests too).
//
// Inputs are the SAME per-frame hand parameters the 2D avatar uses
// (avatar2d.frames_json -> frame.Rq / frame.Lq):
//     { c: [thumb, index, middle, ring, pinky] curls 0..1, s: spread 0..1,
//       x, y: wrist in signing space (100x100, y down, shoulders at y=44, 40 wide),
//       r: finger direction in degrees (0 = up, +90 = viewer's right),
//       p: palm facing (+1 toward the viewer, -1 away) }
// The rig turns them into a full 3D pose: two-bone arm IK, wrist orientation,
// 15 finger joints per hand. It can also go the other way (retarget), turning
// MediaPipe landmarks into the same parameters so the avatar can mirror a person.

import { Object3D, Vector3, Quaternion, Matrix4, MathUtils } from "../lib/three-bundle.min.js";

const D2R = Math.PI / 180;

export const BODY = {
  shoulderY: 1.40,        // world height of the shoulder line (m); 1 signing unit = 1 cm
  shoulderHalf: 0.19,
  headY: 1.66,
  upperArm: 0.27,
  foreArm: 0.25,
  chestZ: 0.12,           // front surface of the torso
};

export const FINGERS = ["thumb", "index", "middle", "ring", "pinky"];
const LEN = {
  thumb: [0.036, 0.030, 0.025],
  index: [0.045, 0.028, 0.022],
  middle: [0.050, 0.032, 0.024],
  ring: [0.046, 0.030, 0.022],
  pinky: [0.036, 0.022, 0.020],
};
const BASE_X = { index: 0.032, middle: 0.011, ring: -0.011, pinky: -0.032 };   // right hand; thumb side = +x
const BASE_Y = { index: 0.092, middle: 0.096, ring: 0.093, pinky: 0.086 };
const BENDS = [70, 95, 60];
const SPREAD = { index: [-2, -8], middle: [0, 0], ring: [1, 6], pinky: [4, 14] };   // [at s=0, extra at s=1]
export const HAND = { LEN, BASE_X, BASE_Y, palmW: 0.09, palmH: 0.095, palmD: 0.032 };

const sstep = (a, b, v) => { const t = MathUtils.clamp((v - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };

// ------------------------------------------------------------------ signing space -> world
export function signingToWorld(x, y, side) {
  const X = (x - 50) * 0.01;
  const Y = BODY.shoulderY - (y - 44) * 0.01;
  const nearFace = (1 - sstep(34, 42, y)) * (1 - sstep(14, 22, Math.abs(x - 50)));
  const nearChest = sstep(40, 48, y) * (1 - sstep(66, 76, y)) * (1 - sstep(10, 18, Math.abs(x - 50)));
  const farSide = sstep(20, 34, Math.abs(x - 50));
  const rest = sstep(72, 80, y);
  let z = 0.30;
  z = MathUtils.lerp(z, 0.23, nearFace);          // in front of the (big cartoon) face
  z = MathUtils.lerp(z, 0.21, nearChest);
  z = MathUtils.lerp(z, 0.16, farSide);
  z = MathUtils.lerp(z, 0.04, rest);
  let wx = X;
  const wy = MathUtils.lerp(Y, BODY.shoulderY - 0.47, rest);     // arms hang (almost) straight at rest
  // at rest the hands hang beside the hips, not inside them
  const outward = side === "R" ? -1 : 1;
  const minOut = 0.24 * rest;
  if (wx * outward < minOut) wx = MathUtils.lerp(wx, outward * minOut, rest);
  return new Vector3(wx, wy, z);
}

// ------------------------------------------------------------------ arm IK
export function shoulderOf(side) {
  return new Vector3(side === "R" ? -BODY.shoulderHalf : BODY.shoulderHalf, BODY.shoulderY - 0.01, 0.0);
}

export function solveArm(side, target) {
  const S = shoulderOf(side);
  const L1 = BODY.upperArm, L2 = BODY.foreArm;
  const d = target.clone().sub(S);
  let dist = d.length();
  const dhat = dist > 1e-6 ? d.clone().divideScalar(dist) : new Vector3(0, -1, 0);
  dist = MathUtils.clamp(dist, 0.06, L1 + L2 - 1e-3);
  const W = S.clone().addScaledVector(dhat, dist);
  const a = (L1 * L1 - L2 * L2 + dist * dist) / (2 * dist);
  const h = Math.sqrt(Math.max(L1 * L1 - a * a, 0));
  const out = side === "R" ? -1 : 1;
  const pole = new Vector3(out * 0.8, -1, 0.1).normalize();     // elbows drop and flare slightly outward
  const pp = pole.clone().addScaledVector(dhat, -pole.dot(dhat));
  if (pp.lengthSq() < 1e-8) pp.set(out, 0, 0);
  pp.normalize();
  const E = S.clone().addScaledVector(dhat, a).addScaledVector(pp, h);
  return { S, E, W, reached: d.length() <= L1 + L2 };
}

// ------------------------------------------------------------------ wrist orientation
export function handQuaternion(side, rDeg, palm) {
  const r = rDeg * D2R;
  const up = Math.cos(r);
  const tilt = up > 0 ? 0.35 : 0.08;                   // raised hands lean a little toward the viewer
  const d = new Vector3(Math.sin(r), Math.cos(r), tilt).normalize();
  const p = MathUtils.clamp(palm, -1, 1);
  // medial direction (toward the body midline), perpendicular to d: R -> d x z, L -> z x d
  const Z = new Vector3(0, 0, 1);
  const m = side === "R" ? new Vector3().crossVectors(d, Z) : new Vector3().crossVectors(Z, d);
  m.normalize();
  const n0 = new Vector3(0, 0, 1).multiplyScalar(p).addScaledVector(m, Math.sqrt(Math.max(1 - p * p, 0)));
  const n = n0.addScaledVector(d, -n0.dot(d)).normalize();
  const x = new Vector3().crossVectors(d, n).normalize();
  const M = new Matrix4().makeBasis(x, d, n);
  return new Quaternion().setFromRotationMatrix(M);
}

// ------------------------------------------------------------------ hand skeleton
// Joint order follows MediaPipe: 0 wrist, 1-4 thumb, 5-8 index, 9-12 middle, 13-16 ring, 17-20 pinky.
export class HandRig {
  constructor(side) {
    this.side = side;
    const sx = side === "R" ? 1 : -1;
    this.root = new Object3D();              // at the wrist; local +Y fingers, +Z palm normal
    this.root.name = `hand_${side}`;
    this.joints = new Array(21);
    this.joints[0] = this.root;
    this.chains = {};
    // thumb
    const tb = new Object3D();
    tb.position.set(sx * 0.030, 0.022, 0.012);
    this.root.add(tb);
    this.chains.thumb = this._chain(tb, LEN.thumb, 1);
    // fingers
    FINGERS.slice(1).forEach((f, k) => {
      const base = new Object3D();
      base.position.set(sx * BASE_X[f], BASE_Y[f], 0);
      this.root.add(base);
      this.chains[f] = this._chain(base, LEN[f], 5 + 4 * k);
    });
    this.setShape([0, 0, 0, 0, 0], 0);
  }

  _chain(base, lens, j0) {
    // j0 = MediaPipe index of the chain's first joint (MCP / CMC)
    this.joints[j0] = base;
    const segs = [];
    let parent = base;
    lens.forEach((L, i) => {
      const seg = new Object3D();          // rotates at this joint
      parent.add(seg);
      const tip = new Object3D();
      tip.position.set(0, L, 0);
      seg.add(tip);
      this.joints[j0 + i + 1] = tip;
      segs.push({ seg, tip, L });
      parent = tip;
    });
    return { base, segs };
  }

  setShape(curls, spread) {
    const sx = this.side === "R" ? 1 : -1;
    const [ct, ...cf] = curls;
    FINGERS.slice(1).forEach((f, k) => {
      const c = MathUtils.clamp(cf[k], 0, 1);
      const ch = this.chains[f];
      const [a0, a1] = SPREAD[f];
      ch.base.rotation.set(0, 0, sx * (a0 + a1 * spread) * D2R);
      ch.segs.forEach((s, i) => s.seg.rotation.set(c * BENDS[i] * D2R, 0, 0));
    });
    // thumb: opens outward at c=0, swings across the palm as it curls
    const c = MathUtils.clamp(ct, 0, 1);
    const th = this.chains.thumb;
    th.base.rotation.set((5 + 20 * c) * D2R, 0, sx * (-45 + 85 * c) * D2R);
    th.segs[0].seg.rotation.set(0, 0, 0);
    th.segs[1].seg.rotation.set(c * 15 * D2R, 0, 0);
    th.segs[2].seg.rotation.set(c * 25 * D2R, 0, 0);
  }

  worldJoints() {
    this.root.updateWorldMatrix(true, true);
    return this.joints.map(j => j.getWorldPosition(new Vector3()));
  }
}

// ------------------------------------------------------------------ whole-body pose from one frame
export function neutralFace() {
  return { brow: "neutral", head: "neutral", mouth: "neutral", hx: 0, hy: 0 };
}

export function solveFrame(frame) {
  // frame: { Rq, Lq, face }
  const out = {};
  for (const side of ["R", "L"]) {
    const q = frame[side + "q"];
    const target = signingToWorld(q.x, q.y, side);
    // keep hands out of the chest
    if (Math.abs(target.x) < 0.17 && target.y < BODY.shoulderY + 0.02 && target.y > 0.95) {
      target.z = Math.max(target.z, BODY.chestZ + 0.07);
    }
    const arm = solveArm(side, target);
    out[side] = { ...arm, T: target, quat: handQuaternion(side, q.r, q.p), curls: q.c, spread: q.s };
  }
  out.face = frame.face || neutralFace();
  return out;
}

export function lerpParams(a, b, t) {
  const L = (u, v) => u + (v - u) * t;
  let dr = ((b.r - a.r + 540) % 360) - 180;          // shortest turn
  return { c: a.c.map((v, i) => L(v, b.c[i])), s: L(a.s, b.s), x: L(a.x, b.x), y: L(a.y, b.y),
           r: a.r + dr * t, p: L(a.p, b.p) };
}

// ------------------------------------------------------------------ synthetic "camera" (tests / self-calibration)
export const CAM = { w: 640, h: 480, spanX: 1.2, centerY: 1.30 };

export function project(v, cam = CAM) {
  const spanY = cam.spanX * cam.h / cam.w;
  return [0.5 + v.x / cam.spanX, 0.5 - (v.y - cam.centerY) / spanY, -v.z / cam.spanX];
}

export function wireFrameFromRig(hands, solved, t = 0, cam = CAM) {
  // hands: {R: HandRig, L: HandRig} already posed at solved.R / solved.L
  const out = { type: "frame", t, w: cam.w, h: cam.h, hands: [], pose: null, face: null, mirrored: false };
  const pose = Array.from({ length: 25 }, () => [0, 0, 0, 0]);
  const put = (i, v) => { const p = project(v, cam); pose[i] = [p[0], p[1], p[2], 0.99]; };
  put(0, new Vector3(0, BODY.headY - 0.025, 0.15));
  put(12, shoulderOf("R")); put(11, shoulderOf("L"));
  put(14, solved.R.E); put(13, solved.L.E);
  put(16, solved.R.W); put(15, solved.L.W);
  out.pose = pose;
  for (const side of ["R", "L"]) {
    const lm = hands[side].worldJoints().map(v => project(v, cam));
    // MediaPipe labels assume a mirrored image: the person's right hand is labelled "Left"
    out.hands.push({ lm, label: side === "R" ? "Left" : "Right", score: 0.99 });
  }
  const nose = project(new Vector3(0, BODY.headY - 0.025, 0.15), cam);
  out.face = { bs: {}, nose: [nose[0], nose[1]] };
  return out;
}

// ------------------------------------------------------------------ retarget: MediaPipe -> params
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const norm = a => Math.hypot(a[0], a[1], a[2]);
const ang = (a, b) => Math.acos(MathUtils.clamp(dot(a, b) / (norm(a) * norm(b) + 1e-9), -1, 1)) / D2R;

let CAL = null;
function calibrate() {
  // Measure our own rig so the inverse mapping is exactly consistent with it.
  const measure = (side, c, p) => {
    const hr = new HandRig(side);
    hr.setShape([c, 0, 0, 0, 0], 0);
    const q = handQuaternion(side, 0, p);
    hr.root.position.set(0, 1.3, 0.3);
    hr.root.quaternion.copy(q);
    const lm = hr.worldJoints().map(v => project(v));
    return lm;
  };
  const thumbRatio = lm => norm(sub(lm[4], lm[17])) / norm(sub(lm[9], lm[0]));
  const crossSign = lm => {
    const a = sub(lm[5], lm[0]), b = sub(lm[17], lm[0]);
    return Math.sign(a[0] * b[1] - a[1] * b[0]);
  };
  const r0 = measure("R", 0, 1), r1 = measure("R", 1, 1);
  CAL = { thumb0: thumbRatio(r0), thumb1: thumbRatio(r1),
          palmSignR: crossSign(r0), palmSignL: crossSign(measure("L", 0, 1)) };
  return CAL;
}
export function calibration() { return CAL || calibrate(); }

export function handParamsFromLandmarks(lm, side, toSpace, aspect) {
  // lm: 21 x [x, y, z] image-normalised (unmirrored). toSpace: (x_img, y_img) -> [sx, sy]
  const cal = calibration();
  const P = lm.map(p => [p[0] * aspect, p[1], (p[2] || 0) * aspect]);
  const chains = [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12], [13, 14, 15, 16], [17, 18, 19, 20]];
  const curls = [0, 0, 0, 0, 0];
  for (let f = 1; f < 5; f++) {
    const [m, p, d, t] = chains[f];
    const total = ang(sub(P[m], P[0]), sub(P[p], P[m])) + ang(sub(P[p], P[m]), sub(P[d], P[p])) +
                  ang(sub(P[d], P[p]), sub(P[t], P[d]));
    curls[f] = MathUtils.clamp((total - 8) / (BENDS[0] + BENDS[1] + BENDS[2] - 8), 0, 1);
  }
  const tr = norm(sub(P[4], P[17])) / (norm(sub(P[9], P[0])) + 1e-9);
  curls[0] = MathUtils.clamp((tr - cal.thumb0) / (cal.thumb1 - cal.thumb0), 0, 1);
  const spreadAng = ang(sub(P[6], P[5]), sub(P[18], P[17]));
  const s = MathUtils.clamp((spreadAng - 6) / 22, 0, 1);
  const v = sub(P[9], P[0]);
  const r = Math.atan2(v[0], -v[1]) / D2R;
  const a = sub(P[5], P[0]), b = sub(P[17], P[0]);
  const cross = (a[0] * b[1] - a[1] * b[0]) / (Math.hypot(a[0], a[1]) * Math.hypot(b[0], b[1]) + 1e-9);
  const sign = side === "R" ? cal.palmSignR : cal.palmSignL;
  const p = MathUtils.clamp(sign * cross * 2.2, -1, 1);
  const [x, y] = toSpace(lm[0][0], lm[0][1]);
  return { c: curls, s, x, y, r, p };
}

export function makeSpaceMapper(frame) {
  // Same idea as setu/perceive/landmarks.py: shoulders define the signing space.
  const aspect = frame.w / frame.h;
  let midX = 0.5 * aspect, midY = 0.45, sw = 0.28 * aspect, ok = false;
  const pz = frame.pose;
  if (pz && pz[11] && pz[12] && Math.min(pz[11][3] ?? 1, pz[12][3] ?? 1) > 0.5) {
    const ax = pz[11][0] * aspect, bx = pz[12][0] * aspect;
    midX = (ax + bx) / 2; midY = (pz[11][1] + pz[12][1]) / 2;
    sw = Math.hypot(ax - bx, pz[11][1] - pz[12][1]); ok = sw > 1e-3;
  }
  const f = (xi, yi) => [50 + (xi * aspect - midX) / sw * 40, 44 + (yi - midY) / sw * 40];
  f.ok = ok; f.aspect = aspect; f.sw = sw; f.mid = [midX, midY];
  return f;
}

export function retargetFrame(frame, { mirror = false, prev = null } = {}) {
  // Wire frame -> {Rq, Lq, face}. mirror=true makes the avatar behave like a mirror image.
  const map = makeSpaceMapper(frame);
  const out = { Rq: prev ? prev.Rq : null, Lq: prev ? prev.Lq : null, face: neutralFace(), seen: { R: false, L: false } };
  const pw = {};
  if (frame.pose) {
    if ((frame.pose[16]?.[3] ?? 0) > 0.3) pw.R = map(frame.pose[16][0], frame.pose[16][1]);
    if ((frame.pose[15]?.[3] ?? 0) > 0.3) pw.L = map(frame.pose[15][0], frame.pose[15][1]);
  }
  for (const h of frame.hands || []) {
    const w = map(h.lm[0][0], h.lm[0][1]);
    let side = /left/i.test(h.label) ? "R" : "L";            // label assumes a mirrored image
    if (pw.R && pw.L) {
      const dR = Math.hypot(w[0] - pw.R[0], w[1] - pw.R[1]), dL = Math.hypot(w[0] - pw.L[0], w[1] - pw.L[1]);
      side = dR <= dL ? "R" : "L";
    }
    let q = handParamsFromLandmarks(h.lm, side, map, map.aspect);
    let target = side;
    if (mirror) {
      target = side === "R" ? "L" : "R";
      q = { ...q, x: 100 - q.x, r: -q.r };
    }
    out[target + "q"] = q;
    out.seen[target] = true;
  }
  const bs = frame.face?.bs || {};
  const up = ((bs.browInnerUp ?? 0) + (bs.browOuterUpLeft ?? 0) + (bs.browOuterUpRight ?? 0)) / 3;
  const down = ((bs.browDownLeft ?? 0) + (bs.browDownRight ?? 0)) / 2;
  out.face.brow = up > 0.35 ? "raised" : down > 0.35 ? "furrowed" : "neutral";
  out.face.mouth = (bs.jawOpen ?? 0) > 0.35 ? "open" : "neutral";
  out.face.smile = ((bs.mouthSmileLeft ?? 0) + (bs.mouthSmileRight ?? 0)) / 2;
  out.face.blink = ((bs.eyeBlinkLeft ?? 0) + (bs.eyeBlinkRight ?? 0)) / 2;
  if (frame.face?.nose && map.ok) {
    const n = map(frame.face.nose[0], frame.face.nose[1]);
    out.face.hx = MathUtils.clamp((n[0] - 50) * (mirror ? -1 : 1), -8, 8);
    out.face.hy = MathUtils.clamp(n[1] - 24, -6, 6);
    out.face.headFree = true;
  }
  return out;
}

export const REST = {
  R: { c: [0.2, 0.3, 0.35, 0.4, 0.45], s: 0.2, x: 36, y: 80, r: 172, p: -1 },
  L: { c: [0.2, 0.3, 0.35, 0.4, 0.45], s: 0.2, x: 64, y: 80, r: -172, p: -1 },
};
