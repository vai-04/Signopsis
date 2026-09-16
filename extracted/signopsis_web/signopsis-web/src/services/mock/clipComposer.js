// Builds an avatar playback clip ({fps,total_ms,frames,segments}, same shape as the backend's
// frames_json) from the recorded per-sign bank. Used by mock mode only.
import BANK from "../../mocks/sign_bank.json";
import { lerpParams } from "../../lib/avatar/rig.js";

const FPS = BANK.fps;
const STEP = 1000 / FPS;
const LEAD_MS = 250, GAP_MS = 170, TAIL_MS = 330;
const NEUTRAL_FACE = { brow: "neutral", head: "neutral", mouth: "neutral", hx: 0, hy: 0 };

const ease = u => u * u * (3 - 2 * u);

function tween(out, a, b, ms, extra) {
  const n = Math.max(1, Math.round(ms / STEP));
  for (let k = 1; k <= n; k++) {
    const u = ease(k / n);
    out.push({ Rq: lerpParams(a.Rq, b.Rq, u), Lq: lerpParams(a.Lq, b.Lq, u), face: u < 0.5 ? a.face : b.face, ...extra });
  }
}

/**
 * @param {import("../../contracts/contracts").GlossItem[]} gloss
 * @param {{question_type?: string|null, negated?: boolean}} [nm]
 * @returns {import("../../contracts/contracts").AvatarClip}
 */
export function composeClip(gloss, nm = {}) {
  const rest = { ...BANK.rest, face: NEUTRAL_FACE };
  const frames = [rest];
  const segments = [];
  let cur = rest;
  gloss.forEach((item, gi) => {
    const faceFor = f => {
      const face = { ...(f.face || NEUTRAL_FACE) };
      if (nm.question_type === "yesno") face.brow = "raised";
      if (nm.question_type === "wh" && gi === gloss.length - 1) { face.brow = "furrowed"; face.head = "tilt_fwd"; }
      if (item.g === "NOT") face.head = "shake";
      return face;
    };
    const clip = item.fingerspelled ? null : BANK.signs[item.g];
    if (clip) {
      const first = { ...clip[0], face: faceFor(clip[0]) };
      tween(frames, cur, first, gi === 0 ? LEAD_MS : GAP_MS, { gi });
      const start = Math.round(frames.length * STEP);
      clip.forEach(f => frames.push({ Rq: f.Rq, Lq: f.Lq, face: faceFor(f), gi }));
      segments.push({ start, end: Math.round(frames.length * STEP), gi, ch: null });
      cur = frames[frames.length - 1];
    } else {
      const letters = item.g.replace(/^FS:/, "").toUpperCase().split("");
      letters.forEach((ch, li) => {
        const shape = BANK.letters[ch] || BANK.letters[String.fromCharCode(65 + (ch.charCodeAt(0) % 26))];
        const pose = { Rq: shape.Rq, Lq: cur.Lq && li > 0 ? cur.Lq : shape.Lq, face: faceFor(shape) };
        tween(frames, cur, pose, li === 0 ? (gi === 0 ? LEAD_MS : GAP_MS) : 90, { gi, ch });
        const start = Math.round(frames.length * STEP);
        const hold = Math.max(2, Math.round((BANK.fs_ms - 90) / STEP));
        for (let k = 0; k < hold; k++) {
          // tiny bounce so held letters don't look frozen
          const b = Math.sin((k / hold) * Math.PI) * 0.6;
          frames.push({ Rq: { ...pose.Rq, y: pose.Rq.y - b }, Lq: pose.Lq, face: pose.face, gi, ch });
        }
        segments.push({ start, end: Math.round(frames.length * STEP), gi, ch });
        cur = frames[frames.length - 1];
      });
    }
  });
  tween(frames, cur, rest, TAIL_MS, { gi: -1 });
  frames.forEach((f, i) => { f.t = Math.round(i * STEP); if (f.gi == null) f.gi = -1; });
  return { fps: FPS, total_ms: Math.round((frames.length - 1) * STEP), frames, segments };
}

export function clipForSign(gloss) {
  const g = gloss.toUpperCase();
  if (!BANK.signs[g]) return null;
  return composeClip([{ g, dur_ms: 0, fingerspelled: false }]);
}

export const bankHasSign = g => !!BANK.signs[g?.toUpperCase?.()];
