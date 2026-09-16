"""2D avatar: SignTarget -> timeline -> landmark frames.

Drop-in stand-in for the SMPL-X avatar. `render_offline` is what the
round-trip gate calls; `frames_json` is what the pixel viewer plays.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from setu.generate.hand2d import REST_L, REST_R, HandPose, pose_to_landmarks
from setu.generate.signs import ALPHABET, FS_DUR, LEXICON, motion
from setu.schemas import NMKey, SignTarget

FPS = 30
LEAD_IN = 250
TRANSITION = 140
TAIL = 350


def _smooth(u: float) -> float:
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def _sample_keys(keys, u: float) -> HandPose:
    if u <= keys[0][0]:
        return keys[0][1]
    for (ta, pa), (tb, pb) in zip(keys, keys[1:]):
        if u <= tb:
            return pa.lerp(pb, _smooth((u - ta) / max(tb - ta, 1e-6)))
    return keys[-1][1]


@dataclass
class Segment:
    start: int
    end: int
    R: list
    L: Optional[list]
    gloss_index: int
    letter: Optional[str] = None

    def pose(self, t: int):
        u = (t - self.start) / max(self.end - self.start, 1)
        r = _sample_keys(self.R, u)
        l = _sample_keys(self.L, u) if self.L else REST_L
        return r, l

    def first(self):
        return self.R[0][1], (self.L[0][1] if self.L else REST_L)

    def last(self):
        return self.R[-1][1], (self.L[-1][1] if self.L else REST_L)


def build_timeline(target: SignTarget) -> tuple[list[Segment], int]:
    """Lay out every gloss (or its fingerspelled letters) on a ms timeline.

    Mutates nothing; returns (segments, total_ms)."""
    segs: list[Segment] = []
    t = LEAD_IN
    for gi, item in enumerate(target.gloss):
        if item.fingerspelled:
            letters = [c for c in (item.fs_fallback or "").split("-") if c in ALPHABET]
            for li, ch in enumerate(letters):
                if li:
                    t += 60                      # short glide between letters
                segs.append(Segment(t, t + FS_DUR, ALPHABET[ch], None, gi, ch))
                t += FS_DUR
        else:
            sign = motion(item.g)
            segs.append(Segment(t, t + item.dur_ms, sign["R"], sign["L"], gi))
            t += item.dur_ms
        t += TRANSITION
    total = t - TRANSITION + TAIL
    return segs, total


def pose_at(segs: list[Segment], t: int) -> tuple[HandPose, HandPose, int, Optional[str]]:
    prev_end, prev_pose = 0, (REST_R, REST_L)
    for s in segs:
        if t < s.start:
            a = _smooth((t - prev_end) / max(s.start - prev_end, 1))
            nr, nl = s.first()
            return prev_pose[0].lerp(nr, a), prev_pose[1].lerp(nl, a), -1, None
        if t <= s.end:
            r, l = s.pose(t)
            return r, l, s.gloss_index, s.letter
        prev_end, prev_pose = s.end, s.last()
    end = prev_end + TAIL
    a = _smooth((t - prev_end) / max(end - prev_end, 1))
    return prev_pose[0].lerp(REST_R, a), prev_pose[1].lerp(REST_L, a), -1, None


def _face_at(nm: list[NMKey], t: int) -> dict:
    state = {"brow": "neutral", "head": "neutral", "mouth": "neutral"}
    for k in nm:
        if k.t > t:
            break
        for f in ("brow", "head", "mouth"):
            v = getattr(k, f)
            if v is not None:
                state[f] = v
    hx = hy = 0.0
    if state["head"] == "shake":
        hx = 2.2 * np.sin(2 * np.pi * t / 300)
    elif state["head"] == "nod":
        hy = 1.6 * abs(np.sin(2 * np.pi * t / 400))
    elif state["head"] == "tilt_fwd":
        hy = 2.0
    state["hx"], state["hy"] = round(float(hx), 2), round(float(hy), 2)
    return state


def render_offline(target: SignTarget, fps: int = FPS):
    """Render to landmark arrays: returns (times[ms], R (N,21,2), L (N,21,2), gloss_idx[N], segs)."""
    segs, total = build_timeline(target)
    times = np.arange(0, total + 1, 1000 / fps)
    R = np.zeros((len(times), 21, 2))
    L = np.zeros((len(times), 21, 2))
    gidx = np.full(len(times), -1)
    for i, t in enumerate(times):
        r, l, gi, _ = pose_at(segs, int(t))
        R[i] = pose_to_landmarks(r, "R")
        L[i] = pose_to_landmarks(l, "L")
        gidx[i] = gi
    return times, R, L, gidx, segs


def _pose_params(p: HandPose) -> dict:
    return {"c": [round(c, 3) for c in p.curl], "s": round(p.spread, 3), "x": round(p.x, 2),
            "y": round(p.y, 2), "r": round(p.rot, 1), "p": round(p.palm, 3)}


def frames_json(target: SignTarget, fps: int = FPS) -> dict:
    """Compact per-frame payload for the pixel viewer."""
    segs, total = build_timeline(target)
    frames = []
    for t in np.arange(0, total + 1, 1000 / fps):
        t = int(t)
        r, l, gi, letter = pose_at(segs, t)
        frames.append({
            "t": t,
            "R": np.round(pose_to_landmarks(r, "R"), 1).tolist(),
            "L": np.round(pose_to_landmarks(l, "L"), 1).tolist(),
            "Rp": round(r.palm, 2), "Lp": round(l.palm, 2),
            "Rq": _pose_params(r), "Lq": _pose_params(l),      # for the 3D avatar (IK driven)
            "gi": gi, "ch": letter,
            "face": _face_at(target.nonmanual, t),
        })
    return {"fps": fps, "total_ms": total, "frames": frames,
            "segments": [{"start": s.start, "end": s.end, "gi": s.gloss_index, "ch": s.letter} for s in segs]}
