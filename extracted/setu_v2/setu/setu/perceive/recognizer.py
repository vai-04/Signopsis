"""L1 sign recognizer: nearest-prototype over landmark sequences.

Architecture section 09 asks for an *embedding* recognizer classified by
nearest prototype so that users can teach signs with no retraining. This is
that design, with DTW over normalised landmark features as the distance.
A learned encoder (ST-GCN) later replaces `embed()` and the distance; the
index, the per-user prototypes and every caller stay the same.

Prototype sources:
  base    one per lexicon sign / fingerspelling letter (from the 2D avatar)
  user    per-user taught samples (name signs, dialect, jargon). These get a
          distance discount so "my" signs win ties.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

import numpy as np

from setu.generate.avatar2d import render_offline
from setu.generate.hand2d import HAND_SCALE
from setu.generate.signs import ALPHABET, FS_DUR, LEXICON
from setu.schemas import GlossItem, SignTarget

K = 16
WRIST_W = 3.0
TAU = 0.08            # softmax temperature over distances (refit: python -m setu.fuse.fit)
USER_DISCOUNT = 0.85  # user prototypes: distance x 0.85
DUR_BETA = 0.04       # duration-mismatch penalty per |log ratio|


def features(R: np.ndarray, L: np.ndarray) -> np.ndarray:
    out = []
    for H in (R, L):
        wrist = H[:, :1, :]
        shape = (H[:, 1:, :] - wrist) / HAND_SCALE
        out.append(wrist.reshape(len(H), -1) / 100.0 * WRIST_W)
        out.append(shape.reshape(len(H), -1))
    return np.concatenate(out, axis=1)


SMOOTH = np.array([1, 2, 3, 2, 1], dtype=float) / 9.0


def smooth_seq(H: np.ndarray) -> np.ndarray:
    """Centered temporal smoothing of (N, ...) landmarks (edge-padded)."""
    n = len(H)
    if n < 3:
        return H
    r = len(SMOOTH) // 2
    pad = np.concatenate([np.repeat(H[:1], r, axis=0), H, np.repeat(H[-1:], r, axis=0)])
    out = np.zeros_like(H, dtype=float)
    for i, w in enumerate(SMOOTH):
        out += w * pad[i:i + n]
    return out


def noise_level(H: np.ndarray) -> float:
    """Robust landmark jitter estimate (signing units) from the high-frequency residual."""
    if len(H) < 6:
        return 0.0
    d2 = H[2:] - 2 * H[1:-1] + H[:-2]           # second difference: noise dominates
    return float(np.median(np.abs(d2)) / 0.6745 / np.sqrt(6))


def resample(x: np.ndarray, k: int = K) -> np.ndarray:
    n = len(x)
    if n == 1:
        return np.repeat(x, k, axis=0)
    pos = np.linspace(0, n - 1, k)
    lo = np.floor(pos).astype(int)
    hi = np.minimum(lo + 1, n - 1)
    w = (pos - lo)[:, None]
    return x[lo] * (1 - w) + x[hi] * w


def resample_batch(F: np.ndarray, starts: np.ndarray, ends: np.ndarray, k: int = K) -> np.ndarray:
    """F: (N, D) frame features. Segment s covers frames [starts[s], ends[s]) -> (S, k, D)."""
    lens = (ends - starts).astype(float)
    pos = starts[:, None] + np.linspace(0, 1, k)[None, :] * (lens[:, None] - 1)
    lo = np.floor(pos).astype(int)
    hi = np.minimum(lo + 1, ends[:, None] - 1)
    w = (pos - lo)[..., None]
    return F[lo] * (1 - w) + F[hi] * w


def dtw_many(Q: np.ndarray, T: np.ndarray, band: int = 4, chunk: int = 128) -> np.ndarray:
    """Q: (S,k,D), T: (M,k,D) -> (S,M) normalised DTW distances."""
    S, k, _ = Q.shape
    M = T.shape[0]
    out = np.empty((S, M))
    t2 = (T ** 2).sum(-1)                           # (M,k)
    for c0 in range(0, S, chunk):
        q = Q[c0:c0 + chunk]
        q2 = (q ** 2).sum(-1)                       # (s,k)
        cross = np.einsum("sid,mjd->smij", q, T, optimize=True)
        cost = np.sqrt(np.maximum(q2[:, None, :, None] + t2[None, :, None, :] - 2 * cross, 0.0))
        s = len(q)
        acc = np.full((s, M, k + 1, k + 1), np.inf)
        acc[:, :, 0, 0] = 0.0
        for i in range(1, k + 1):
            for j in range(max(1, i - band), min(k, i + band) + 1):
                best = np.minimum(np.minimum(acc[:, :, i - 1, j], acc[:, :, i, j - 1]), acc[:, :, i - 1, j - 1])
                acc[:, :, i, j] = cost[:, :, i - 1, j - 1] + best
        out[c0:c0 + chunk] = acc[:, :, k, k] / (2 * k)
    return out


def _lockstep(Q: np.ndarray, T: np.ndarray) -> np.ndarray:
    """No-warp alignment cost, normalised like dtw_many: (S,k,D),(M,k,D) -> (S,M)."""
    q2 = (Q ** 2).sum(-1)                                # (S,k)
    t2 = (T ** 2).sum(-1)                                # (M,k)
    cross = np.einsum("sid,mid->smi", Q, T, optimize=True)
    d = np.sqrt(np.maximum(q2[:, None, :] + t2[None, :, :] - 2 * cross, 0.0))  # (S,M,k)
    return d.sum(-1) / (2 * d.shape[-1])


def _dtw_pairs(Q: np.ndarray, TT: np.ndarray, band: int = 4) -> np.ndarray:
    """Q: (S,k,D), TT: (S,s,k,D) -> (S,s) DTW, each query against its own shortlist."""
    S, k, _ = Q.shape
    s = TT.shape[1]
    q2 = (Q ** 2).sum(-1)
    t2 = (TT ** 2).sum(-1)                               # (S,s,k)
    cross = np.einsum("aid,abjd->abij", Q, TT, optimize=True)
    cost = np.sqrt(np.maximum(q2[:, None, :, None] + t2[:, :, None, :] - 2 * cross, 0.0))
    acc = np.full((S, s, k + 1, k + 1), np.inf)
    acc[:, :, 0, 0] = 0.0
    for i in range(1, k + 1):
        for j in range(max(1, i - band), min(k, i + band) + 1):
            best = np.minimum(np.minimum(acc[:, :, i - 1, j], acc[:, :, i, j - 1]), acc[:, :, i - 1, j - 1])
            acc[:, :, i, j] = cost[:, :, i - 1, j - 1] + best
    return acc[:, :, k, k] / (2 * k)


@dataclass
class Proto:
    label: str
    kind: str                 # "sign" | "letter"
    T: np.ndarray             # (K, D)
    dur_ms: float
    owner: Optional[str] = None


@lru_cache(maxsize=1)
def base_prototypes() -> tuple[Proto, ...]:
    protos = []
    for g, spec in sorted(LEXICON.items()):
        protos.append(Proto(g, "sign", _render(GlossItem(g=g, dur_ms=spec["dur"])), spec["dur"]))
    for ch in sorted(ALPHABET):
        if ch.isdigit():
            continue
        protos.append(Proto(ch, "letter",
                            _render(GlossItem(g="FS", dur_ms=FS_DUR, fingerspelled=True, fs_fallback=ch)), FS_DUR))
    return tuple(protos)


def _render(item: GlossItem) -> np.ndarray:
    t, R, L, _, segs = render_offline(SignTarget(gloss=[item]))
    s = segs[0]
    R, L = smooth_seq(R), smooth_seq(L)
    m = (t >= s.start) & (t <= s.end)
    return resample(features(R[m], L[m]))


@dataclass
class Index:
    protos: list[Proto] = field(default_factory=lambda: list(base_prototypes()))

    def __post_init__(self):
        self._rebuild()

    def _rebuild(self):
        self.T = np.stack([p.T for p in self.protos])
        self.labels = sorted({p.label for p in self.protos})
        self.lab_idx = np.array([self.labels.index(p.label) for p in self.protos])
        self.kind_of = {p.label: p.kind for p in self.protos}
        self.durs = np.array([p.dur_ms for p in self.protos], dtype=float)
        self.discount = np.array([USER_DISCOUNT if p.owner else 1.0 for p in self.protos])
        self.user_labels = {p.label for p in self.protos if p.owner}

    def with_user(self, user_protos: list[Proto]) -> "Index":
        return Index(list(base_prototypes()) + list(user_protos))

    def label_distances(self, Q: np.ndarray, durs_ms: Optional[np.ndarray] = None,
                        shortlist: int = 10) -> np.ndarray:
        """(S,k,D) -> (S, n_labels): best distance per label.

        Two stages: a cheap lock-step (diagonal) distance to every prototype,
        then exact DTW only for each query's `shortlist` nearest. DTW <= the
        lock-step distance, so far prototypes keep their (upper-bound) value."""
        diag = _lockstep(Q, self.T)     # same normalisation as DTW's diagonal path
        if shortlist and shortlist < len(self.protos):
            near = np.argpartition(diag, shortlist, axis=1)[:, :shortlist]          # (S, s)
            D = diag.copy()
            sub_T = self.T[near]                                                     # (S, s, k, D)
            D_near = _dtw_pairs(Q, sub_T)
            np.put_along_axis(D, near, np.minimum(D_near, np.take_along_axis(diag, near, 1)), axis=1)
        else:
            D = dtw_many(Q, self.T)
        D = D * self.discount[None, :]
        if durs_ms is not None:
            D = D + DUR_BETA * np.abs(np.log(np.maximum(durs_ms[:, None], 1) / self.durs[None, :]))
        out = np.full((len(Q), len(self.labels)), np.inf)
        for li in range(len(self.labels)):
            out[:, li] = D[:, self.lab_idx == li].min(axis=1)
        return out

    def probs(self, LD: np.ndarray, tau: float = TAU) -> np.ndarray:
        z = -LD / tau
        z = z - z.max(axis=1, keepdims=True)
        p = np.exp(z)
        return p / p.sum(axis=1, keepdims=True)

    def lattice(self, ld_row: np.ndarray, p_row: np.ndarray, n: int = 3) -> list[tuple[str, float]]:
        order = np.argsort(-p_row)[:n]
        return [(self.labels[i], float(p_row[i])) for i in order]


def dtw_open(A: np.ndarray, B: np.ndarray, k: int = 24, slack: float = 0.3) -> float:
    """Open-begin/open-end DTW between two feature sequences (N,D),(M,D).

    Either sequence may skip up to `slack` of its length at the start and end,
    so spans that include a bit of the neighbouring transition still match.
    Returns the mean per-step cost of the best path."""
    a, b = resample(A, k), resample(B, k)
    C = np.linalg.norm(a[:, None, :] - b[None, :, :], axis=-1)
    s = int(round(slack * k))
    INF = np.inf
    acc = np.full((k, k), INF)
    steps = np.zeros((k, k))
    for i in range(k):
        for j in range(k):
            if (i == 0 and j <= s) or (j == 0 and i <= s):
                acc[i, j], steps[i, j] = C[i, j], 1
                continue
            best, st = INF, 0
            for di, dj in ((1, 0), (0, 1), (1, 1)):
                pi, pj = i - di, j - dj
                if pi >= 0 and pj >= 0 and acc[pi, pj] < INF:
                    v = (acc[pi, pj] + C[i, j]) / (steps[pi, pj] + 1)
                    if v < best:
                        best, st = v, steps[pi, pj] + 1
            if st:
                acc[i, j] = best * st
                steps[i, j] = st
    ends = [(i, k - 1) for i in range(k - 1 - s, k)] + [(k - 1, j) for j in range(k - 1 - s, k)]
    vals = [acc[i, j] / steps[i, j] for i, j in ends if steps[i, j] >= k * (1 - slack)]
    return float(min(vals)) if vals else float("inf")
