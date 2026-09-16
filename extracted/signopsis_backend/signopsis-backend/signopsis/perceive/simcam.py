"""Simulated camera: 2D avatar -> MediaPipe-format wire frames.

This is the inverse of `landmarks.Normalizer`. It lets the whole live
sign -> text path (WebSocket included) run and be tested with no webcam,
under controlled degradations that imitate what MediaPipe does in bad
conditions:

  noise      landmark jitter (signing-space units)
  dropout    per-frame probability a detected hand is lost
  overlap    when hand boxes overlap, MediaPipe often loses one hand
  lux        low light -> more jitter and dropout
  speed      signing speed multiplier
  lefty      mirror the signer (left-handed)
  scale/off  random body size / position in the frame
  mirrored   emit landmarks as a selfie-mirrored client would
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from signopsis.generate.avatar2d import frames_json
from signopsis.generate.signs import FS_DUR, LEXICON, UNLISTED, fs_letters, motion
from signopsis.perceive.landmarks import SHOULDER_W, SHOULDER_Y, bbox_iou, hand_bbox
from signopsis.schemas import GlossItem, NMKey, SignTarget


@dataclass
class Degrade:
    noise: float = 0.4
    dropout: float = 0.0
    overlap_drop: float = 0.0
    lux: float = 140.0
    speed: float = 1.0
    lefty: bool = False
    mirrored: bool = False
    body_scale: float = 1.0
    body_dx: float = 0.0
    body_dy: float = 0.0
    idle_ms: int = 1100           # hands-down tail so the phrase closes on its own
    hide_rest_hands: bool = True  # hands at rest usually leave the frame

    @classmethod
    def random(cls, rng: np.random.Generator, severity: float) -> "Degrade":
        """severity 0 (studio) .. 1 (awful)."""
        s = severity
        lux = float(np.clip(rng.normal(150 - 120 * s, 15), 5, 255))
        return cls(noise=float(0.3 + 3.2 * s * rng.uniform(0.5, 1.2)),
                   dropout=float(np.clip(0.35 * s * rng.uniform(0.3, 1.3), 0, 0.6)),
                   overlap_drop=float(0.8 * s),
                   lux=lux,
                   speed=float(rng.uniform(0.85, 1.25)),
                   lefty=bool(rng.random() < 0.15),
                   mirrored=bool(rng.random() < 0.5),
                   body_scale=float(rng.uniform(0.8, 1.2)),
                   body_dx=float(rng.uniform(-0.1, 0.1)),
                   body_dy=float(rng.uniform(-0.05, 0.05)))


def plan_for(glosses: list[str], nonmanual: Optional[list[NMKey]] = None) -> SignTarget:
    items = []
    for g in glosses:
        if g.startswith("FS:"):
            letters = fs_letters(g[3:])
            n = len(letters.split("-"))
            items.append(GlossItem(g=g, dur_ms=n * FS_DUR, fingerspelled=True, fs_fallback=letters))
        else:
            items.append(GlossItem(g=g, dur_ms=motion(g)["dur"]))
    return SignTarget(gloss=items, nonmanual=nonmanual or [])


BLEND = {
    "raised":   {"browInnerUp": 0.75, "browOuterUpLeft": 0.7, "browOuterUpRight": 0.7, "browDownLeft": 0.02, "browDownRight": 0.02},
    "furrowed": {"browInnerUp": 0.05, "browOuterUpLeft": 0.02, "browOuterUpRight": 0.02, "browDownLeft": 0.7, "browDownRight": 0.7},
    "neutral":  {"browInnerUp": 0.08, "browOuterUpLeft": 0.05, "browOuterUpRight": 0.05, "browDownLeft": 0.08, "browDownRight": 0.08},
}


def stream(target: SignTarget, deg: Degrade = Degrade(), seed: int = 0, w: int = 640, h: int = 480,
           fps: int = 30, t0: float = 0.0) -> list[dict]:
    """Return a list of WireFrame dicts (JSON-ready)."""
    rng = np.random.default_rng(seed)
    fj = frames_json(target, fps=fps)
    frames = fj["frames"]
    aspect = w / h
    sw = 0.30 * aspect * deg.body_scale                   # shoulder width, iso units
    mid = np.array([0.5 * aspect + deg.body_dx, 0.52 + deg.body_dy])

    lux_pen = float(np.clip((60 - deg.lux) / 60, 0, 1))  # darkness penalty
    noise = deg.noise * (1 + 1.5 * lux_pen)
    dropout = min(0.9, deg.dropout + 0.35 * lux_pen)

    def to_img(pts):
        pts = np.asarray(pts, dtype=np.float64)
        x = pts[..., 0]
        if deg.lefty:
            x = 100.0 - x
        xi = mid[0] + (x - 50.0) / SHOULDER_W * sw
        yi = mid[1] + (pts[..., 1] - SHOULDER_Y) / SHOULDER_W * sw
        xn = xi / aspect
        if deg.mirrored:
            xn = 1.0 - xn
        return np.stack([xn, yi], axis=-1)

    out = []
    dt = 1000.0 / fps / deg.speed
    n_idle = int(deg.idle_ms / (1000.0 / fps))
    rest = frames[-1]
    seq = frames + [dict(rest, gi=-1, t=rest["t"]) for _ in range(n_idle)]
    for k, f in enumerate(seq):
        t = t0 + k * dt
        R = np.asarray(f["R"]) + rng.normal(0, noise, (21, 2))
        L = np.asarray(f["L"]) + rng.normal(0, noise, (21, 2))
        if deg.lefty:            # signer's dominant hand is now their left
            sides = [("L_dom", R), ("R_nd", L)]
        else:
            sides = [("R_dom", R), ("L_nd", L)]
        keep = []
        at_rest = f["gi"] < 0
        iou = bbox_iou(hand_bbox(R), hand_bbox(L))
        for name, H in sides:
            if deg.hide_rest_hands and at_rest and H[0, 1] > 76:
                continue
            if rng.random() < dropout:
                continue
            if iou > 0.15 and name.endswith("nd") and rng.random() < deg.overlap_drop:
                continue
            keep.append((name, H))
        hands = []
        for name, H in keep:
            img = to_img(H)
            person_side_right = name.startswith("R")      # which of the person's hands
            # MediaPipe label assumes a mirrored image
            if deg.mirrored:
                label = "Right" if person_side_right else "Left"
            else:
                label = "Left" if person_side_right else "Right"
            lm = [[float(x), float(y), 0.0] for x, y in img]
            hands.append({"lm": lm, "label": label, "score": float(np.clip(0.95 - noise * 0.05, 0.3, 1))})

        # pose: nose, shoulders, elbows, wrists (MediaPipe indices)
        face = f["face"]
        nose_s = np.array([50 + face["hx"], 24 + face["hy"]])
        pose = [[0.0, 0.0, 0.0, 0.0] for _ in range(25)]

        def put(idx, pt, vis=0.99):
            p = to_img(np.asarray(pt, dtype=np.float64) + rng.normal(0, noise * 0.3, 2))
            pose[idx] = [float(p[0]), float(p[1]), 0.0, vis]

        put(0, nose_s)
        # person's right shoulder is at avatar x=30 (before lefty mirroring handled in to_img)
        put(12, (30, SHOULDER_Y)); put(11, (70, SHOULDER_Y))
        rw = np.asarray(f["R"])[0]; lw = np.asarray(f["L"])[0]
        if deg.lefty:   # to_img mirrors x, so R (dominant) lands on the person's left
            put(15, rw); put(16, lw)
            put(13, (np.array([70, SHOULDER_Y]) + rw) / 2 + [0, 8]); put(14, (np.array([30, SHOULDER_Y]) + lw) / 2 + [0, 8])
            put(11, (30, SHOULDER_Y)); put(12, (70, SHOULDER_Y))
        else:
            put(16, rw); put(15, lw)
            put(14, (np.array([30, SHOULDER_Y]) + rw) / 2 + [0, 8]); put(13, (np.array([70, SHOULDER_Y]) + lw) / 2 + [0, 8])
        if deg.mirrored:       # a mirrored image swaps which side each shoulder appears on, not its identity
            pass
        nose_img = to_img(nose_s + rng.normal(0, 0.15 + noise * 0.1, 2))
        bs = dict(BLEND.get(face["brow"], BLEND["neutral"]))
        bs = {k: float(np.clip(v + rng.normal(0, 0.04), 0, 1)) for k, v in bs.items()}
        bs["jawOpen"] = 0.5 if face.get("mouth") == "open" else 0.05
        bs["cheekPuff"] = 0.6 if face.get("mouth") == "puffed" else 0.02
        face_ok = rng.random() > dropout * 0.5
        out.append({
            "type": "frame", "t": round(t, 1), "w": w, "h": h,
            "hands": hands, "pose": pose,
            "face": {"bs": bs, "nose": [float(nose_img[0]), float(nose_img[1])]} if face_ok else None,
            "lux": float(np.clip(deg.lux + rng.normal(0, 3), 0, 255)),
            "mirrored": deg.mirrored,
            "_gi": f["gi"],       # ground truth (ignored by the server), handy for debugging
        })
    return out


def text_stream(text: str, deg: Degrade = Degrade(), seed: int = 0, **kw) -> tuple[list[dict], dict]:
    """Text -> pipeline D plan -> simulated camera. Returns (frames, info)."""
    from signopsis.pipeline import text_to_sign
    res = text_to_sign(text, seed=seed)
    sign = next(t for t in res["plan"]["targets"] if t["kind"] == "sign")
    tgt = SignTarget.model_validate(sign)
    frames = stream(tgt, deg, seed=seed, **kw)
    return frames, {"gloss": res["frame"]["gloss"], "signed": [g["g"] if not g["fingerspelled"] else "FS:" + (g["fs_fallback"] or "").replace("-", "") for g in sign["gloss"]],
                    "question_type": res["frame"]["question_type"], "negated": res["frame"]["negated"]}
