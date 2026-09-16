// node tests/js/rig.test.mjs  -> exits non-zero on failure
import assert from "node:assert/strict";
import { Vector3 } from "three";
import * as R from "../src/lib/avatar/rig.js";

let n = 0;
const test = (name, fn) => { fn(); n++; console.log("ok -", name); };

function pose(frame) {
  const solved = R.solveFrame(frame);
  const hands = { R: new R.HandRig("R"), L: new R.HandRig("L") };
  for (const s of ["R", "L"]) {
    hands[s].setShape(solved[s].curls, solved[s].spread);
    hands[s].root.position.copy(solved[s].W);
    hands[s].root.quaternion.copy(solved[s].quat);
  }
  return { solved, hands };
}

test("arm IK keeps bone lengths and reaches reachable targets", () => {
  for (const side of ["R", "L"]) {
    for (const [x, y] of [[40, 62], [48, 30], [24, 60], [36, 80], [60, 50], [14, 56], [47, 14]]) {
      const t = R.signingToWorld(x, y, side);
      const a = R.solveArm(side, t);
      assert.ok(Math.abs(a.E.distanceTo(a.S) - R.BODY.upperArm) < 1e-6);
      assert.ok(Math.abs(a.E.distanceTo(a.W) - R.BODY.foreArm) < 1e-6);
      if (a.reached) assert.ok(a.W.distanceTo(t) < 1e-6);
      assert.ok(a.E.y < a.S.y + 0.15, `elbow too high for ${x},${y}: ${a.E.y}`);
    }
  }
});

test("hand basis is anatomical: thumb points to the midline when the palm faces the viewer", () => {
  for (const side of ["R", "L"]) {
    const h = new R.HandRig(side);
    h.setShape([0, 0, 0, 0, 0], 0);
    h.root.position.set(side === "R" ? -0.2 : 0.2, 1.3, 0.3);
    h.root.quaternion.copy(R.handQuaternion(side, 0, 1));
    const j = h.worldJoints();
    const midward = side === "R" ? 1 : -1;
    assert.ok((j[4].x - j[0].x) * midward > 0, `${side} thumb tip should be medial`);
    assert.ok(j[12].y > j[0].y + 0.15, "fingers point up");
    // in hand space the palm normal is +z: curling must move the fingertips to +z and closer to the wrist
    const g = new R.HandRig(side);
    g.setShape([0, 1, 1, 1, 1], 0);
    const k = g.worldJoints();
    assert.ok(k[8].z > 0.02 && k[8].y < 0.1, `curled tip ${k[8].toArray()}`);
  }
});

test("retarget(project(pose)) recovers the pose", () => {
  const cases = [
    { c: [0, 0, 0, 0, 0], s: 0, x: 40, y: 58, r: 10, p: 1 },
    { c: [1, 0, 1, 1, 1], s: 0, x: 44, y: 50, r: -30, p: 1 },
    { c: [0.55, 1, 1, 1, 1], s: 0, x: 38, y: 60, r: 0, p: -1 },
    { c: [0, 0, 0, 0, 0], s: 1, x: 42, y: 46, r: 60, p: 1 },
    { c: [0.75, 0.78, 0.78, 0.78, 0.78], s: 0, x: 46, y: 64, r: 90, p: -1 },
  ];
  for (const q of cases) {
    const frame = { Rq: q, Lq: R.REST.L };
    const { solved, hands } = pose(frame);
    const wire = R.wireFrameFromRig(hands, solved);
    const back = R.retargetFrame(wire);
    const g = back.Rq;
    assert.ok(g, "right hand found");
    const tgt = R.signingToWorld(q.x, q.y, "R");
    // wrist position (IK may clamp unreachable targets; compare against where the wrist really is)
    const W = solved.R.W;
    const wx = W.x / 0.01 + 50, wy = (R.BODY.shoulderY - W.y) / 0.01 + 44;
    assert.ok(Math.abs(g.x - wx) < 1.5 && Math.abs(g.y - wy) < 1.5, `wrist ${g.x},${g.y} vs ${wx},${wy}`);
    for (let f = 1; f < 5; f++) assert.ok(Math.abs(g.c[f] - q.c[f]) < 0.2, `curl ${f}: ${g.c[f]} vs ${q.c[f]}`);
    assert.ok(Math.abs(g.c[0] - q.c[0]) < 0.3, `thumb ${g.c[0]} vs ${q.c[0]}`);
    assert.ok(Math.sign(g.p) === Math.sign(q.p), `palm ${g.p} vs ${q.p}`);
    const dr = Math.abs(((g.r - q.r + 540) % 360) - 180);
    assert.ok(dr < 25, `rot ${g.r} vs ${q.r}`);
  }
});

test("mirror mode swaps hands and reflects", () => {
  const q = { c: [0, 0, 0, 0, 0], s: 0, x: 38, y: 50, r: 20, p: 1 };
  const { solved, hands } = pose({ Rq: q, Lq: R.REST.L });
  const back = R.retargetFrame(R.wireFrameFromRig(hands, solved), { mirror: true });
  assert.ok(back.Lq.x > 55 && back.Lq.r < 0);
});

test("parameter interpolation takes the short way round", () => {
  const a = { c: [0, 0, 0, 0, 0], s: 0, x: 0, y: 0, r: 170, p: 1 };
  const b = { ...a, r: -170 };
  assert.ok(Math.abs(R.lerpParams(a, b, 0.5).r) > 175);
});

console.log(`${n} rig tests passed`);
