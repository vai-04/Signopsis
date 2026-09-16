"""L2: uncertainty fusion and calibration (architecture section 04).

  quality = σ(q · [vis, overlap, jitter, dark, anchor] + q0)
  trust   = σ( w1·margin_cal + w2·quality − w3·disagreement − w4·novelty + b )

  gate = emit   if trust ≥ 0.75
         repair if 0.40 ≤ trust < 0.75
         hold   if trust < 0.40

Weights are fitted by logistic regression against "was the top-1 correct"
(python -m signopsis.fuse.fit) and stored in weights.json next to this file.
Until fitted, hand-set defaults are used.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import numpy as np

WEIGHTS_PATH = Path(__file__).with_name("weights.json")
EMIT_AT, HOLD_BELOW = 0.75, 0.40
COVERAGE_HOLD, COVERAGE_REPAIR = 0.40, 0.65   # share of signing time explained by recognised signs (fit: exact p5=0.72, deletions p95=0.58)
HIGH_STAKES_BUMP = 0.10

QUALITY_KEYS = ("vis", "overlap", "jitter", "dark", "anchor")
DEFAULT = {
    "quality": {"w": [3.0, -3.0, -1.2, -2.5, 1.0], "b": -0.5},
    "trust": {"w": [5.0, 2.0, 2.0, 3.0, 0.5], "b": -2.2},   # margin, quality, -disagreement, -novelty, -fs
    "tau": 0.08,
    "fitted": False,
}


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.asarray(x, dtype=float)))


@dataclass
class SlotSignals:
    margin: float            # calibrated p1 - p2
    vis: float               # fraction of span frames with the dominant hand detected
    overlap: float           # mean hand-box IoU
    jitter: float            # estimated landmark noise (signing units)
    dark: float              # 0 bright .. 1 very dark
    anchor: float            # fraction of frames with a body anchor
    disagreement: float      # mean pairwise KL across temporal crops
    novelty: float           # best distance / novelty threshold (>1 = unknown)
    fs: float = 0.0          # 1 if this slot is a fingerspelled word

    def quality_vec(self) -> np.ndarray:
        return np.array([self.vis, self.overlap, min(self.jitter, 5.0) / 5.0, self.dark, self.anchor])

    def to_dict(self) -> dict:
        return {k: round(float(v), 4) for k, v in asdict(self).items()}


class TrustModel:
    def __init__(self, weights: Optional[dict] = None):
        if weights is None:
            weights = DEFAULT
            if WEIGHTS_PATH.exists():
                try:
                    weights = json.loads(WEIGHTS_PATH.read_text())
                except Exception:
                    weights = DEFAULT
        self.W = weights

    @property
    def tau(self) -> float:
        return float(self.W.get("tau", DEFAULT["tau"]))

    def quality(self, s: SlotSignals) -> float:
        q = self.W["quality"]
        return float(sigmoid(np.dot(q["w"], s.quality_vec()) + q["b"]))

    def trust_vec(self, s: SlotSignals, margin: Optional[float] = None) -> np.ndarray:
        m = s.margin if margin is None else margin
        return np.array([m, self.quality(s), -min(s.disagreement, 3.0), -max(0.0, s.novelty - 0.6), -s.fs])

    def trust(self, s: SlotSignals, margin: Optional[float] = None) -> float:
        t = self.W["trust"]
        return float(sigmoid(np.dot(t["w"], self.trust_vec(s, margin)) + t["b"]))


def thresholds(high_stakes: bool) -> tuple[float, float]:
    bump = HIGH_STAKES_BUMP if high_stakes else 0.0
    return EMIT_AT + bump, HOLD_BELOW + bump


def gate_for(trust: float, high_stakes: bool = False) -> str:
    emit, hold = thresholds(high_stakes)
    if trust >= emit:
        return "emit"
    if trust >= hold:
        return "repair"
    return "hold"


def hold_reason(s: SlotSignals, lux: Optional[float]) -> tuple[str, str]:
    """(code, human message) for a 'didn't catch that' prompt. Most specific cause first."""
    if lux is not None and lux < 40:
        return "dark", "It's too dark. Add some light and sign it again."
    if s.anchor < 0.5:
        return "no_body", "I can't see your shoulders. Move back a little so your upper body is in view."
    if s.vis < 0.6:
        return "hands_lost", "I lost your hands. Keep them inside the frame and sign it again."
    if s.overlap > 0.25:
        return "overlap", "Your hands overlapped, so I couldn't tell them apart. Please sign it again."
    if s.jitter > 2.5:
        return "blur", "The video is too shaky or blurry. Please sign it again, a little slower."
    if s.novelty > 1.0:
        return "unknown", "I don't know that sign yet."
    return "unsure", "I didn't catch that. Please sign it again."
