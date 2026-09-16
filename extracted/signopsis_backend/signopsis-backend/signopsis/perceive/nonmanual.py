"""Non-manual markers and prosody from the face / head / signing dynamics.

Grammar lives in the face (section 05-A):
  brows raised over the phrase  -> yes/no question
  brows furrowed                -> wh-question
  head shake during a sign      -> negation of that sign
  head nod                      -> affirmation
Prosody for sign -> voice (section 05-B) comes from signing speed and size
relative to the signer's OWN rolling baseline, never from a guess.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from signopsis.perceive.landmarks import Obs
from signopsis.schemas import NonManual, Prosody


@dataclass
class Baseline:
    """Per-user rolling baselines (EMA)."""
    brow_up: float = 0.10
    brow_down: float = 0.10
    speed: Optional[float] = None       # signing units / s
    amplitude: Optional[float] = None   # signing units
    n_phrases: int = 0
    alpha: float = 0.15

    def update_face(self, obs: Obs):
        """Call on frames where the person is NOT signing (neutral face)."""
        a = 0.02
        if obs.brow_up is not None:
            self.brow_up = (1 - a) * self.brow_up + a * obs.brow_up
        if obs.brow_down is not None:
            self.brow_down = (1 - a) * self.brow_down + a * obs.brow_down

    def update_motion(self, speed: float, amp: float):
        if self.speed is None:
            self.speed, self.amplitude = speed, amp
        else:
            self.speed = (1 - self.alpha) * self.speed + self.alpha * speed
            self.amplitude = (1 - self.alpha) * self.amplitude + self.alpha * amp
        self.n_phrases += 1


def _osc_energy(x: np.ndarray, t: np.ndarray) -> tuple[float, int]:
    """Amplitude and number of direction reversals of a detrended 1-D signal."""
    if len(x) < 6:
        return 0.0, 0
    k = min(len(x), 9)
    trend = np.convolve(np.pad(x, (k // 2, k // 2), mode="edge"), np.ones(k) / k, mode="valid")[: len(x)]
    r = x - trend
    v = np.diff(r)
    v = v[np.abs(v) > 0.15]
    rev = int(np.sum(np.sign(v[1:]) != np.sign(v[:-1]))) if len(v) > 1 else 0
    return float(np.percentile(np.abs(r), 90)), rev


@dataclass
class NMResult:
    phrase: NonManual
    question: Optional[str]                     # "yesno" | "wh" | None (from the face alone)
    shake_spans: list[tuple[float, float]] = field(default_factory=list)
    nod: bool = False
    prosody: Prosody = field(default_factory=Prosody)
    face_coverage: float = 0.0


def analyse(frames: list[Obs], base: Baseline, update: bool = True) -> NMResult:
    t = np.array([f.t for f in frames], dtype=float)
    ups = np.array([f.brow_up if f.brow_up is not None else np.nan for f in frames])
    downs = np.array([f.brow_down if f.brow_down is not None else np.nan for f in frames])
    cover = float(np.mean(~np.isnan(ups))) if len(ups) else 0.0

    brow, question = "neutral", None
    conf = 0.0
    if cover > 0.3:
        up_rel = np.nanmean(ups) - base.brow_up
        down_rel = np.nanmean(downs) - base.brow_down
        frac_up = np.nanmean((ups - base.brow_up) > 0.25)
        frac_down = np.nanmean((downs - base.brow_down) > 0.25)
        if frac_up > 0.45 and up_rel > down_rel:
            brow, question = "raised", "yesno"
            conf = float(min(1.0, frac_up) * cover)
        elif frac_down > 0.45:
            brow, question = "furrowed", "wh"
            conf = float(min(1.0, frac_down) * cover)
        else:
            conf = float(cover * (1 - max(frac_up, frac_down)))

    # head movement from the nose track
    shake_spans, head, nod = [], "neutral", False
    # head movement: only the face-mesh nose (pose nose is too coarse), and only
    # oscillation well above this track's own jitter
    noses = [(f.t, f.extra["nose_raw"]) for f in frames if "nose_raw" in f.extra]
    face_frac = len(noses) / max(len(frames), 1)
    if len(noses) >= 8 and face_frac >= 0.6:
        tn = np.array([a for a, _ in noses])
        xy = np.array([b for _, b in noses])
        d2 = xy[2:, 0] - 2 * xy[1:-1, 0] + xy[:-2, 0]
        sig = float(np.median(np.abs(d2)) / 0.6745 / np.sqrt(6)) if len(d2) else 0.0
        amp_min = max(0.9, 4.0 * sig)
        # sliding windows of ~600 ms
        win = 18
        for s in range(0, max(1, len(xy) - win + 1), 6):
            ax, rx = _osc_energy(xy[s:s + win, 0], tn[s:s + win])
            if ax > amp_min and rx >= 3:
                shake_spans.append((float(tn[s]), float(tn[min(s + win, len(tn)) - 1])))
        ay, ry = _osc_energy(xy[:, 1], tn)
        ax_all, _ = _osc_energy(xy[:, 0], tn)
        if shake_spans:
            head = "shake"
        elif ay > max(0.8, 4.0 * sig) and ry >= 2 and ax_all < 0.6:
            head, nod = "nod", True
    # merge overlapping shake spans
    merged = []
    for a, b in shake_spans:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))

    # mouth
    jaw = [f.jaw_open for f in frames if f.jaw_open is not None]
    puff = [f.cheek_puff for f in frames if f.cheek_puff is not None]
    mouth = "neutral"
    if puff and np.mean(puff) > 0.35:
        mouth = "puffed"
    elif jaw and np.mean(jaw) > 0.35:
        mouth = "open"

    # prosody vs the signer's own baseline
    W = np.array([f.R[0] for f in frames if f.R is not None])
    tw = np.array([f.t for f in frames if f.R is not None])
    prosody = Prosody(conf=0.3)
    if len(W) >= 5 and tw[-1] > tw[0]:
        path = float(np.linalg.norm(np.diff(W, axis=0), axis=1).sum())
        speed = path / ((tw[-1] - tw[0]) / 1000.0)
        amp = float(np.linalg.norm(W.std(axis=0)))
        if base.speed:
            sr, ar = speed / base.speed, amp / max(base.amplitude, 1e-6)
            pace = "fast" if sr > 1.3 else "slow" if sr < 0.75 else "normal"
            intensity = float(np.clip(0.3 + 0.5 * (sr - 1) + 0.3 * (ar - 1), 0.05, 1.0))
            affect = "urgent" if (sr > 1.35 and ar > 1.1) else "neutral"
            conf_p = float(min(0.9, 0.3 + 0.1 * base.n_phrases))
            if conf_p < 0.5:
                affect = "neutral"          # never guess affect before we know the signer
            prosody = Prosody(affect=affect, intensity=intensity, pace=pace, conf=conf_p)
        if update:
            base.update_motion(speed, amp)

    return NMResult(NonManual(brow=brow, head=head, mouth=mouth, conf=round(conf, 3)),
                    question, merged, nod, prosody, cover)
