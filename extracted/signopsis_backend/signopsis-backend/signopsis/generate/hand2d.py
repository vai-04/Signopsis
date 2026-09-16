"""2D parametric hand model -> MediaPipe-format landmarks.

A hand pose is (handshape, location, rotation, palm). Forward kinematics
projects a 3D-ish finger fold onto the 2D front plane, producing the same
21-point layout MediaPipe Hands emits:

   0 wrist | 1-4 thumb | 5-8 index | 9-12 middle | 13-16 ring | 17-20 pinky

Signing space is 100 x 100 units, x to the viewer's right, y down.
The signer faces the viewer, so the signer's RIGHT (dominant) hand appears
on the viewer's LEFT (x < 50).

This is the stand-in for the SMPL-X avatar: the round-trip gate, recognizer
and viewer only ever see landmarks, so swapping in SMPL-X later means
replacing `pose_to_landmarks` with "render SMPL-X, project joints".
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

HAND_SCALE = 11.0

# curls: thumb, index, middle, ring, pinky (0 = extended, 1 = fully folded)
HANDSHAPES: dict[str, dict] = {
    "FLAT":  {"curl": [0.0, 0.0, 0.0, 0.0, 0.0], "spread": 0.0},
    "OPEN":  {"curl": [0.0, 0.0, 0.0, 0.0, 0.0], "spread": 1.0},
    "FIST":  {"curl": [0.55, 1.0, 1.0, 1.0, 1.0], "spread": 0.0},
    "POINT": {"curl": [1.0, 0.0, 1.0, 1.0, 1.0], "spread": 0.0},
    "V":     {"curl": [1.0, 0.0, 0.0, 1.0, 1.0], "spread": 1.0},
    "H":     {"curl": [1.0, 0.0, 0.0, 1.0, 1.0], "spread": 0.0},
    "Y":     {"curl": [0.0, 1.0, 1.0, 1.0, 0.0], "spread": 1.0},
    "L":     {"curl": [0.0, 0.0, 1.0, 1.0, 1.0], "spread": 1.0},
    "C":     {"curl": [0.3, 0.5, 0.5, 0.5, 0.5], "spread": 0.0},
    "O":     {"curl": [0.75, 0.78, 0.78, 0.78, 0.78], "spread": 0.0},
    "THUMB": {"curl": [0.0, 1.0, 1.0, 1.0, 1.0], "spread": 0.0},
    "W":     {"curl": [1.0, 0.0, 0.0, 0.0, 1.0], "spread": 1.0},
    "I":     {"curl": [1.0, 1.0, 1.0, 1.0, 0.0], "spread": 0.0},
    "X":     {"curl": [1.0, 0.6, 1.0, 1.0, 1.0], "spread": 0.0},
    "BENT":  {"curl": [0.1, 0.6, 0.6, 0.6, 0.6], "spread": 0.0},
    "REST":  {"curl": [0.2, 0.3, 0.35, 0.4, 0.45], "spread": 0.2},
}

# named locations for the RIGHT hand; left hand mirrors x -> 100 - x
LOCATIONS: dict[str, tuple[float, float]] = {
    "forehead": (47, 14), "temple": (38, 16), "eyes": (46, 20), "nose": (48, 25),
    "mouth": (48, 30), "chin": (48, 34), "cheek": (40, 27), "ear": (37, 23),
    "head_side": (30, 18), "above_head": (40, 4),
    "shoulder": (34, 44), "chest": (46, 54), "chest_c": (50, 54), "heart": (56, 52),
    "stomach": (48, 70), "neutral": (40, 62), "front": (46, 64), "front_high": (42, 46),
    "side": (24, 60), "side_high": (24, 42), "far_side": (14, 56),
    "low": (40, 78), "rest": (36, 80), "fs": (34, 50), "center": (50, 62),
}

BASES = {  # hand-local (fingers up = -y), unit = HAND_SCALE
    "thumb": (-0.25, -0.15), "index": (-0.28, -0.75), "middle": (-0.07, -0.80),
    "ring": (0.13, -0.75), "pinky": (0.32, -0.65),
}
DIRS = {"index": -8.0, "middle": 0.0, "ring": 6.0, "pinky": 14.0}
SPREAD = {"index": -10.0, "middle": 0.0, "ring": 8.0, "pinky": 16.0}
LENGTHS = {
    "index": (0.42, 0.26, 0.20), "middle": (0.46, 0.30, 0.22),
    "ring": (0.42, 0.28, 0.20), "pinky": (0.32, 0.20, 0.18),
    "thumb": (0.30, 0.28, 0.22),
}
BENDS = (70.0, 95.0, 60.0)  # max fold per joint, degrees


@dataclass(frozen=True)
class HandPose:
    curl: tuple[float, ...]
    spread: float
    x: float
    y: float
    rot: float          # degrees; 0 = fingers up, +90 = fingers to viewer's right
    palm: float = 1.0   # +1 palm to viewer, -1 back of hand to viewer (interpolates)

    @staticmethod
    def make(shape: str, loc, rot: float = 0.0, palm: str = "out", side: str = "R",
             dx: float = 0.0, dy: float = 0.0) -> "HandPose":
        hs = HANDSHAPES[shape]
        x, y = LOCATIONS[loc] if isinstance(loc, str) else loc
        x, y = x + dx, y + dy
        if side == "L":
            x, rot = 100 - x, -rot
        return HandPose(tuple(hs["curl"]), hs["spread"], x, y, rot, 1.0 if palm == "out" else -1.0)

    def lerp(self, other: "HandPose", a: float) -> "HandPose":
        b = 1 - a
        return HandPose(
            tuple(p * b + q * a for p, q in zip(self.curl, other.curl)),
            self.spread * b + other.spread * a,
            self.x * b + other.x * a, self.y * b + other.y * a,
            self.rot + (((other.rot - self.rot + 180) % 360) - 180) * a,   # shortest turn
            self.palm * b + other.palm * a,
        )


def _finger(base, ang_deg, lengths, curl):
    pts = []
    x, y = base
    ux, uy = math.sin(math.radians(ang_deg)), -math.cos(math.radians(ang_deg))
    cum = 0.0
    pts.append((x, y))
    for L, B in zip(lengths, BENDS):
        cum += curl * B
        proj = L * math.cos(math.radians(cum))
        x, y = x + ux * proj, y + uy * proj
        pts.append((x, y))
    return pts  # 4 points: MCP, PIP, DIP, TIP


def _thumb(curl):
    x, y = BASES["thumb"]
    pts = [(x, y)]
    ang = -50.0 + curl * 115.0      # swings across the palm as it curls
    for i, L in enumerate(LENGTHS["thumb"]):
        a = ang + i * curl * 25.0
        L = L * (1 - 0.25 * curl)
        x, y = x + math.sin(math.radians(a)) * L, y - math.cos(math.radians(a)) * L
        pts.append((x, y))
    return pts  # CMC, MCP, IP, TIP


def pose_to_landmarks(p: HandPose, side: str = "R") -> np.ndarray:
    """Return (21, 2) landmark array in signing-space units."""
    local = [(0.0, 0.0)] + _thumb(p.curl[0])
    for i, f in enumerate(("index", "middle", "ring", "pinky")):
        ang = DIRS[f] + SPREAD[f] * p.spread
        local += _finger(BASES[f], ang, LENGTHS[f], p.curl[i + 1])
    arr = np.array(local, dtype=np.float64)
    # palm facing: back of hand mirrors the local x axis; left hand mirrors again
    mirror = p.palm * (-1.0 if side == "L" else 1.0)
    arr[:, 0] *= mirror
    th = math.radians(p.rot)
    c, s = math.cos(th), math.sin(th)
    rot = np.array([[c, -s], [s, c]])
    arr = arr @ rot.T
    return arr * HAND_SCALE + np.array([p.x, p.y])


REST_R = HandPose.make("REST", "rest", rot=172, palm="in", side="R")
REST_L = HandPose.make("REST", "rest", rot=172, palm="in", side="L")


def with_offset(p: HandPose, dx: float, dy: float) -> HandPose:
    return replace(p, x=p.x + dx, y=p.y + dy)
