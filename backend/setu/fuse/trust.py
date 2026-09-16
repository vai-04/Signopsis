"""trust = sigmoid(w1*margin_cal + w2*quality - w3*disagreement + b)  (Section 5).

Until eval/ fits real weights these are config defaults and the result is
marked `calibrated=False` so S20 can say so.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .. import config
from ..schemas import LatticeSlot, PerceptEvent, Quality


@dataclass
class TrustWeights:
    margin: float = config.TRUST_W_MARGIN
    quality: float = config.TRUST_W_QUALITY
    disagreement: float = config.TRUST_W_DISAGREE
    bias: float = config.TRUST_BIAS
    temperature: float = config.TRUST_TEMPERATURE
    calibrated: bool = config.TRUST_CALIBRATED


@dataclass
class TrustResult:
    value: float
    margin: float
    quality: float
    disagreement: float
    slot_margins: list[float] = field(default_factory=list)
    calibrated: bool = False


def temperature_scale(scores: list[float], t: float) -> list[float]:
    if t == 1.0 or not scores:
        return list(scores)
    powered = [max(s, 1e-12) ** (1.0 / t) for s in scores]
    z = sum(powered)
    # Keep any mass the lattice left unassigned ("some other word").
    return [p / z * min(1.0, sum(scores)) for p in powered]


def slot_margin(slot: LatticeSlot, t: float = 1.0) -> float:
    scores = temperature_scale(sorted((c.score for c in slot.cands), reverse=True), t)
    if not scores:
        return 0.0
    p1 = scores[0]
    # Unassigned mass ("some other word") is spread over unseen rivals; count
    # a fixed share of it as the strongest one.
    unassigned = max(0.0, 1.0 - sum(scores)) * config.UNSEEN_RIVAL_SHARE
    p2 = max(scores[1], unassigned) if len(scores) > 1 else unassigned
    return max(0.0, p1 - p2)


def quality_score(q: Quality) -> float:
    """Heuristic quality in [0,1]; replaced by quality_model.py once trained."""
    parts: list[float] = []
    if q.snr_db is not None:
        parts.append(min(1.0, max(0.0, (q.snr_db - 5.0) / 20.0)))
    if q.landmark_vis is not None:
        parts.append(q.landmark_vis)
    if q.hand_overlap is not None:
        parts.append(1.0 - q.hand_overlap)
    if q.motion_blur is not None:
        parts.append(1.0 - q.motion_blur)
    return sum(parts) / len(parts) if parts else 0.5


def compute_trust(event: PerceptEvent, disagreement: float = 0.0, w: TrustWeights | None = None) -> TrustResult:
    w = w or TrustWeights()
    margins = [slot_margin(s, w.temperature) for s in event.lattice if s.cands]
    # An utterance is only as trustworthy as its weakest word.
    margin = min(margins) if margins else 0.0
    quality = quality_score(event.quality)
    z = w.margin * margin + w.quality * quality - w.disagreement * disagreement + w.bias
    value = 1.0 / (1.0 + math.exp(-z))
    return TrustResult(value, margin, quality, disagreement, margins, w.calibrated)
