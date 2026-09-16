"""Round-trip gate (architecture section 07).

Render the planned signing -> landmarks -> recognizer -> did it read back
as the gloss we meant? Signs that don't read back confidently are replaced
by fingerspelling and the caption is forced on.

The recognizer here is a nearest-template DTW classifier over landmark
sequences, i.e. the same *interface* as the real L1 embedding recognizer
(landmarks in, lattice out). Swap `Recognizer` for the ST-GCN model later;
the gate code does not change.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from setu.generate.avatar2d import render_offline
from setu.generate.hand2d import HAND_SCALE
from setu.generate.signs import ALPHABET, FS_DUR, LEXICON
from setu.schemas import GlossItem, LatticeSlot, SignTarget

K = 12                 # resample length
WRIST_W = 3.0          # weight of absolute hand location vs handshape
TAU = 0.08             # softmax temperature (refit with: python -m setu.eval.calibrate)
NOISE_SIGMA = 0.45     # landmark jitter in signing-space units (simulated perception)
TRIALS = 3             # noisy re-reads (ensemble, like the offset crops in section 04)
SEG_SLOP_MS = 60       # segmentation error: window bleeds into transitions
THRESHOLD = 0.70
THRESHOLD_HIGH_STAKES = 0.85


def features(R: np.ndarray, L: np.ndarray) -> np.ndarray:
    """(N,21,2)x2 -> (N, 84)."""
    out = []
    for H in (R, L):
        wrist = H[:, :1, :]
        shape = (H[:, 1:, :] - wrist) / HAND_SCALE
        out.append(wrist.reshape(len(H), -1) / 100.0 * WRIST_W)
        out.append(shape.reshape(len(H), -1))
    return np.concatenate(out, axis=1)


def resample(x: np.ndarray, k: int = K) -> np.ndarray:
    if len(x) == 1:
        return np.repeat(x, k, axis=0)
    src = np.linspace(0, 1, len(x))
    dst = np.linspace(0, 1, k)
    return np.stack([np.interp(dst, src, x[:, d]) for d in range(x.shape[1])], axis=1)


def dtw_batch(q: np.ndarray, T: np.ndarray) -> np.ndarray:
    """q: (K,D), T: (M,K,D) -> (M,) normalized DTW distance, vectorized over templates."""
    cost = np.linalg.norm(T[:, None, :, :] - q[None, :, None, :], axis=-1)  # (M,K,K)
    M, n, m = cost.shape
    acc = np.full((M, n + 1, m + 1), np.inf)
    acc[:, 0, 0] = 0.0
    for i in range(1, n + 1):
        for j in range(max(1, i - 3), min(m, i + 3) + 1):   # Sakoe-Chiba band
            best = np.minimum(np.minimum(acc[:, i - 1, j], acc[:, i, j - 1]), acc[:, i - 1, j - 1])
            acc[:, i, j] = cost[:, i - 1, j - 1] + best
    return acc[:, n, m] / (n + m)


def _isolated(g: str, fingerspell: bool) -> np.ndarray:
    if fingerspell:
        item = GlossItem(g="FS", dur_ms=FS_DUR, fingerspelled=True, fs_fallback=g)
    else:
        item = GlossItem(g=g, dur_ms=LEXICON[g]["dur"])
    t, R, L, gidx, segs = render_offline(SignTarget(gloss=[item]))
    s = segs[0]
    mask = (t >= s.start) & (t <= s.end)
    return resample(features(R[mask], L[mask]))


@dataclass
class Bank:
    labels: list[str]
    T: np.ndarray


@lru_cache(maxsize=2)
def template_bank(kind: str) -> Bank:
    if kind == "sign":
        labels = sorted(LEXICON)
        return Bank(labels, np.stack([_isolated(g, False) for g in labels]))
    labels = sorted(ALPHABET)
    return Bank(labels, np.stack([_isolated(c, True) for c in labels]))


class Recognizer:
    """Landmarks in, lattice out.

    Design section 07: the round-trip gate reads the avatar with the SAME L1
    recognizer the live camera uses (setu.perceive.recognizer), restricted to
    signs or to fingerspelling letters. `legacy=True` keeps the original
    standalone template matcher for comparison."""

    def __init__(self, tau: float = TAU, legacy: bool = False):
        self.tau = tau
        self.legacy = legacy

    def classify(self, R, L, kind: str = "sign") -> list[tuple[str, float]]:
        if self.legacy:
            bank = template_bank(kind)
            q = resample(features(R, L))
            d = dtw_batch(q, bank.T)
            labels = bank.labels
        else:
            from setu.perceive.recognizer import Index, features as f2, resample as r2, smooth_seq
            idx = _shared_index()
            q = r2(f2(smooth_seq(R), smooth_seq(L)))
            LD = idx.label_distances(q[None])[0]
            want = "letter" if kind == "letter" else "sign"
            keep = [i for i, g in enumerate(idx.labels) if idx.kind_of[g] == want]
            d = LD[keep]
            labels = [idx.labels[i] for i in keep]
        z = -np.asarray(d) / self.tau
        p = np.exp(z - z.max())
        p /= p.sum()
        order = np.argsort(-p)[:3]
        return [(labels[i], float(p[i])) for i in order]


@lru_cache(maxsize=1)
def _shared_index():
    from setu.perceive.recognizer import Index
    return Index()


@dataclass
class GateResult:
    target: SignTarget
    lattices: list[LatticeSlot]          # what the recognizer read back, per gloss
    readback: list[str]                  # top-1 per gloss (letters joined for fingerspelling)
    degraded: list[int]                  # gloss indices switched to fingerspelling
    score: float                         # sequence round-trip score


def _read(target: SignTarget, rng, recog: Recognizer):
    times, R, L, gidx, segs = render_offline(target)
    per_gloss_p: dict[int, list[float]] = {}
    lattices: dict[int, list] = {}
    readback: dict[int, list[str]] = {}
    for s in segs:
        m = (times >= s.start - SEG_SLOP_MS) & (times <= s.end + SEG_SLOP_MS)
        intended = s.letter if s.letter else target.gloss[s.gloss_index].g
        kind = "letter" if s.letter else "sign"
        ps, tops, lat_acc = [], [], {}
        for _ in range(TRIALS):
            Rn = R[m] + rng.normal(0, NOISE_SIGMA, R[m].shape)
            Ln = L[m] + rng.normal(0, NOISE_SIGMA, L[m].shape)
            lat = recog.classify(Rn, Ln, kind)
            probs = dict(lat)
            ps.append(probs.get(intended, 0.0))
            tops.append(lat[0][0])
            for g, p in lat:
                lat_acc[g] = lat_acc.get(g, 0.0) + p / TRIALS
        per_gloss_p.setdefault(s.gloss_index, []).append(float(np.mean(ps)))
        top = max(set(tops), key=tops.count)
        readback.setdefault(s.gloss_index, []).append(top)
        lattices.setdefault(s.gloss_index, []).append(sorted(lat_acc.items(), key=lambda kv: -kv[1])[:3])
    return per_gloss_p, lattices, readback


def roundtrip_gate(target: SignTarget, threshold: float = THRESHOLD, seed: int = 7,
                   recog: Recognizer | None = None) -> GateResult:
    recog = recog or Recognizer()
    rng = np.random.default_rng(seed)
    per, lats, rb = _read(target, rng, recog)

    degraded = []
    for gi, item in enumerate(target.gloss):
        if item.fingerspelled:
            continue
        p = per.get(gi, [0.0])[0]
        if p < threshold and item.fs_fallback:
            item.fingerspelled = True
            degraded.append(gi)

    if degraded:  # re-read the degraded plan so scores describe what will actually play
        per, lats, rb = _read(target, np.random.default_rng(seed), recog)

    scores = []
    lattice_slots = []
    readback = []
    for gi, item in enumerate(target.gloss):
        ps = per.get(gi, [0.0])
        item.roundtrip = round(float(min(ps)), 3)   # a word is only as clear as its worst letter
        scores.append(item.roundtrip)
        cands = lats.get(gi, [[("?", 0.0)]])
        lattice_slots.append(LatticeSlot(slot=gi, cands=[(g, round(p, 3)) for g, p in cands[0]]))
        tops = rb.get(gi, ["?"])
        readback.append("".join(tops) if item.fingerspelled else tops[0])
    target.roundtrip_score = round(float(np.mean(scores)) if scores else 0.0, 3)
    return GateResult(target, lattice_slots, readback, degraded, target.roundtrip_score)
