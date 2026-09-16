"""L0 -> L1 adapter: MediaPipe wire frames -> body-centred signing space.

Signing space is the same 100 x 100 space the 2D avatar uses: shoulders at
y = 44 and 40 units apart, the head centred at (50, 22), and the signer's
RIGHT hand on the viewer's LEFT. Normalising real camera landmarks into
this space is what lets the avatar templates, user-taught prototypes and
the round-trip gate all share one recognizer.

Handedness: MediaPipe labels assume a mirrored (selfie) image. For an
unmirrored frame its "Left" is the signer's right hand. We prefer the pose
wrists (15 = left, 16 = right) when they are visible and only fall back to
the label.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from setu.generate.hand2d import REST_L, REST_R, pose_to_landmarks
from setu.schemas import WireFrame

SHOULDER_Y = 44.0
SHOULDER_W = 40.0
NOSE_TO_SHOULDER = 20.0      # signing-space units from the nose down to the shoulder line
P_NOSE, P_LSH, P_RSH, P_LWR, P_RWR = 0, 11, 12, 15, 16

REST_R_LM = pose_to_landmarks(REST_R, "R")
REST_L_LM = pose_to_landmarks(REST_L, "L")

BROW_UP = ("browInnerUp", "browOuterUpLeft", "browOuterUpRight")
BROW_DOWN = ("browDownLeft", "browDownRight")


@dataclass
class Obs:
    """One normalised observation (a video frame after L0)."""
    t: float
    R: Optional[np.ndarray] = None       # (21, 2) signing space, dominant hand
    L: Optional[np.ndarray] = None       # (21, 2) non-dominant hand
    r_score: float = 0.0
    l_score: float = 0.0
    anchor_ok: bool = False
    brow_up: Optional[float] = None
    brow_down: Optional[float] = None
    cheek_puff: Optional[float] = None
    jaw_open: Optional[float] = None
    nose: Optional[np.ndarray] = None    # (2,) signing space
    lux: Optional[float] = None
    extra: dict = field(default_factory=dict)

    @property
    def hands_present(self) -> int:
        return int(self.R is not None) + int(self.L is not None)


class Normalizer:
    """Stateful: smooths the body anchor so the signing space doesn't wobble."""

    def __init__(self, dominant: str = "right", alpha: float = 0.3):
        self.dominant = dominant
        self.alpha = alpha
        self.mid: Optional[np.ndarray] = None   # (x_iso, y) of the shoulder midpoint
        self.sw: Optional[float] = None         # shoulder width in iso units
        self.prev: dict = {}                    # last hand centroid per side (continuity)

    # -- anchors -----------------------------------------------------------
    def _update_anchor(self, f: WireFrame, aspect: float) -> bool:
        pose = f.pose
        if pose and len(pose) > P_RSH:
            ls, rs = pose[P_LSH], pose[P_RSH]
            vis = min(ls[3] if len(ls) > 3 else 1.0, rs[3] if len(rs) > 3 else 1.0)
            if vis > 0.5:
                a = np.array([ls[0] * aspect, ls[1]])
                b = np.array([rs[0] * aspect, rs[1]])
                mid, sw = (a + b) / 2, float(np.linalg.norm(a - b))
                if sw > 1e-3:
                    self._blend(mid, sw)
                    return True
        # fallback: nose, keep the previous scale
        nose = None
        if f.face and f.face.nose:
            nose = f.face.nose
        elif pose and len(pose) > 0 and (len(pose[0]) < 4 or pose[0][3] > 0.5):
            nose = pose[0][:2]
        if nose is not None:
            sw = self.sw or 0.28 * aspect
            mid = np.array([nose[0] * aspect, nose[1] + sw * NOSE_TO_SHOULDER / SHOULDER_W])
            self._blend(mid, sw)
            return False
        if self.mid is None:          # never saw a body: assume a centred signer
            self.mid, self.sw = np.array([0.5 * aspect, 0.45]), 0.28 * aspect
        return False

    def _blend(self, mid, sw):
        if self.mid is None:
            self.mid, self.sw = mid, sw
        else:
            a = self.alpha
            self.mid = (1 - a) * self.mid + a * mid
            self.sw = (1 - a) * self.sw + a * sw

    def to_space(self, xy_iso: np.ndarray) -> np.ndarray:
        out = np.empty_like(xy_iso, dtype=np.float64)
        out[..., 0] = 50.0 + (xy_iso[..., 0] - self.mid[0]) / self.sw * SHOULDER_W
        out[..., 1] = SHOULDER_Y + (xy_iso[..., 1] - self.mid[1]) / self.sw * SHOULDER_W
        return out

    # -- handedness ----------------------------------------------------------
    def _assign(self, hands, pw, mirrored, t=0.0) -> dict:
        """Assign up to two detected hands to R/L minimising
        pose-wrist distance + temporal continuity + label disagreement."""
        def label_side(h):
            if not h.label:
                return None
            is_left = h.label.lower() == "left"
            # MediaPipe's label assumes a mirrored (selfie) image
            return ("L" if is_left else "R") if mirrored else ("R" if is_left else "L")

        def cost(lm, h, side):
            c = 0.0
            if side in pw:
                c += min(float(np.linalg.norm(lm[0] - pw[side])), 40.0)
            prev = self.prev.get(side)
            if prev is not None and t - prev[1] <= 300:
                c += 0.7 * min(float(np.linalg.norm(lm.mean(0) - prev[0])), 40.0)
            else:
                c += 0.7 * 15.0                       # no recent track: neutral
            ls = label_side(h)
            if ls is not None and ls != side:
                c += 10.0
            if side not in pw and ls is None:
                c += 0.0 if (lm[0, 0] < 50) == (side == "R") else 5.0
            return c

        hands = sorted(hands, key=lambda x: -x[1].score)[:2]
        best, best_c = {}, float("inf")
        if len(hands) == 1:
            for side in ("R", "L"):
                c = cost(hands[0][0], hands[0][1], side)
                if c < best_c:
                    best, best_c = {side: (hands[0][0], hands[0][1].score)}, c
        elif len(hands) == 2:
            (l0, h0), (l1, h1) = hands
            for s0, s1 in (("R", "L"), ("L", "R")):
                c = cost(l0, h0, s0) + cost(l1, h1, s1)
                if c < best_c:
                    best, best_c = {s0: (l0, h0.score), s1: (l1, h1.score)}, c
        for side in best:
            self.prev[side] = (best[side][0].mean(0), t)
        return best

    # -- main --------------------------------------------------------------
    def __call__(self, f: WireFrame) -> Obs:
        aspect = f.w / max(f.h, 1)
        anchor_ok = self._update_anchor(f, aspect)
        obs = Obs(t=f.t, anchor_ok=anchor_ok, lux=f.lux)

        def iso(pts):
            a = np.asarray(pts, dtype=np.float64)[..., :2].copy()
            if f.mirrored:
                a[..., 0] = 1.0 - a[..., 0]
            a[..., 0] *= aspect
            return a

        hands = []
        for h in f.hands:
            if len(h.lm) != 21:
                continue
            hands.append((self.to_space(iso(h.lm)), h))

        # pose wrists (signing space) for handedness
        pw = {}
        if f.pose and len(f.pose) > P_RWR:
            for side, idx in (("R", P_RWR), ("L", P_LWR)):
                p = f.pose[idx]
                if len(p) < 4 or p[3] > 0.3:
                    pw[side] = self.to_space(iso(np.array(p[:2])))

        assigned = self._assign(hands, pw, f.mirrored, f.t)
        if self.dominant == "left":
            # mirror a left-handed signer onto right-handed templates
            assigned = {("L" if s == "R" else "R"): (_mirror(lm), sc) for s, (lm, sc) in assigned.items()}

        if "R" in assigned:
            obs.R, obs.r_score = assigned["R"]
        if "L" in assigned:
            obs.L, obs.l_score = assigned["L"]

        if f.face:
            bs = f.face.bs or {}
            if bs:
                ups = [bs[k] for k in BROW_UP if k in bs]
                downs = [bs[k] for k in BROW_DOWN if k in bs]
                obs.brow_up = float(np.mean(ups)) if ups else None
                obs.brow_down = float(np.mean(downs)) if downs else None
                obs.cheek_puff = bs.get("cheekPuff")
                obs.jaw_open = bs.get("jawOpen")
            if f.face.nose:
                raw = iso(np.array(f.face.nose[:2]))
                obs.extra["nose_raw"] = raw / self.sw * SHOULDER_W      # head motion w/o anchor jitter
                n = self.to_space(raw)
                obs.nose = _mirror_pt(n) if self.dominant == "left" else n
                obs.extra["nose_src"] = "face"
        elif f.pose and len(f.pose) > 0 and (len(f.pose[0]) < 4 or f.pose[0][3] > 0.5):
            n = self.to_space(iso(np.array(f.pose[0][:2])))
            obs.nose = _mirror_pt(n) if self.dominant == "left" else n
            obs.extra["nose_src"] = "pose"
        return obs


def _mirror(lm: np.ndarray) -> np.ndarray:
    out = lm.copy()
    out[:, 0] = 100.0 - out[:, 0]
    return out


def _mirror_pt(p: np.ndarray) -> np.ndarray:
    return np.array([100.0 - p[0], p[1]])


def hand_bbox(lm: np.ndarray) -> tuple[float, float, float, float]:
    return float(lm[:, 0].min()), float(lm[:, 1].min()), float(lm[:, 0].max()), float(lm[:, 1].max())


def bbox_iou(a, b) -> float:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0
