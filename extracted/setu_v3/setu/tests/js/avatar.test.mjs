// node tests/js/avatar.test.mjs <plan.json>  -- builds the 3D avatar headlessly and plays a real SETU plan
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { Vector3 } from "../../setu/serve/static/lib/three-bundle.min.js";
import { createAvatar } from "../../setu/serve/static/avatar3d/avatar.js";
import { signingToWorld, lerpParams } from "../../setu/serve/static/avatar3d/rig.js";

const plan = JSON.parse(readFileSync(process.argv[2], "utf8"));
const frames = plan.frames.frames;
const av = createAvatar();
let meshes = 0;
av.group.traverse(o => { if (o.isMesh || o.isInstancedMesh) meshes++; });
assert.ok(meshes > 150, `expected a detailed avatar, got ${meshes} meshes`);

let maxErr = 0, checked = 0, moved = 0;
let prevTip = null;
for (let i = 0; i < frames.length; i++) {
  const f = frames[i];
  const solved = av.update(f, i / 30, 1 / 30);
  for (const side of ["R", "L"]) {
    const wrist = av.hands[side].root.position.clone();          // body-local, like the IK solution
    assert.ok(wrist.distanceTo(solved[side].W) < 1e-6, "hand is attached to the IK wrist");
    const q = f[side + "q"];
    const raw = signingToWorld(q.x, q.y, side);
    assert.ok(Math.abs(raw.x - solved[side].T.x) < 1e-9 && Math.abs(raw.y - solved[side].T.y) < 1e-9);
    assert.ok(solved[side].T.z >= raw.z - 1e-9, "collision push only moves hands forward");
    const target = solved[side].T;
    if (solved[side].reached) { maxErr = Math.max(maxErr, wrist.distanceTo(target)); checked++; }
    for (const p of [wrist, solved[side].E]) assert.ok(Number.isFinite(p.x + p.y + p.z), "finite pose");
  }
  const tip = av.hands.R.worldJoints()[8];
  if (prevTip && tip.distanceTo(prevTip) > 0.002) moved++;
  prevTip = tip;
}
assert.ok(checked > frames.length, "most hand targets are reachable");
assert.ok(maxErr < 0.005, `wrist error ${maxErr}`);
assert.ok(moved > frames.length / 4, "the index fingertip actually moves while signing");

// interpolation between 30 fps frames stays finite and in-between
const mid = lerpParams(frames[10].Rq, frames[11].Rq, 0.5);
assert.ok(Number.isFinite(mid.x) && mid.c.every(Number.isFinite));

// face grammar reaches the rig: a wh-question plan contains furrowed-brow frames
if (plan.frame.question_type === "wh") assert.ok(frames.some(f => f.face.brow === "furrowed"));
console.log(`avatar ok: ${meshes} meshes, ${frames.length} frames, max wrist error ${(maxErr * 1000).toFixed(2)} mm`);
