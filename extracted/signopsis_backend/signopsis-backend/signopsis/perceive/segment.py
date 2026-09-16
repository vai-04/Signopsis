"""Streaming phrase tracking + segmentation-free sign decoding.

PhraseTracker   watches normalised frames and cuts the stream into phrases
                (hands up -> signing -> hands down / gone for END_MS).
decode_phrase   level-building dynamic programming over the phrase: every
                candidate span is scored against every prototype at once
                (vectorised DTW), and the cheapest explanation as
                [gap | sign]* wins. Pauses between signs are short and
                unreliable, so we don't depend on them (section 05-A).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from signopsis.perceive.landmarks import REST_L_LM, REST_R_LM, Obs, bbox_iou, hand_bbox
from signopsis.perceive.recognizer import K, Index, features, noise_level, resample_batch, smooth_seq

ACTIVE_Y = 76.0        # a wrist above this line (signing space) = signing
START_FRAMES = 2
END_MS = 450           # hands visibly back at rest this long -> phrase over
END_MS_LOST = 900      # hands simply not detected: wait longer (dropout is not "done")
MAX_PHRASE_MS = 12000
PREROLL = 3

SEG_MIN_MS, SEG_MAX_MS = 150, 1700
GAP_MAX_MS = 700
GAP_BASE = 0.25        # per-frame cost of calling a span "transition", above the noise floor
SEG_PEN = 0.6          # cost per sign (discourages over-segmentation)
MAX_FILL = 6           # frames of missing hand we interpolate across
NOVEL_BASE = 0.30     # best distance above noise floor + this = sign not in the index


def noise_floor(sigma: float) -> float:
    """Expected DTW distance of a CORRECT match at landmark jitter sigma (fit in exp: ~0.29*sigma)."""
    return 0.27 * max(0.0, sigma - 0.15) + 0.05
UNKNOWN_MIN_MS = 350   # a moving stretch this long that matched nothing = unknown sign
UNKNOWN_MIN_MOTION = 8.0


REST_ZONE_Y = 68.0     # wrist below this line = still rising from / falling to rest


def trim_edges(P: "Prepared", a: int, b: int, min_len: int = 2) -> tuple[int, int]:
    """Drop the hands-rising / hands-falling frames at either end of [a, b)."""
    y = P.R[:, 0, 1]
    while b - a > min_len and y[a] > REST_ZONE_Y:
        a += 1
    while b - a > min_len and y[b - 1] > REST_ZONE_Y:
        b -= 1
    return a, b


V_TRAVEL = 2.2         # wrist speed (units/frame) of hands travelling between places


def trim_travel(P: "Prepared", a: int, b: int, min_len: int = 5) -> tuple[int, int]:
    """Strip fast straight travel (rise from rest, fall to rest, transitions) off both ends."""
    w = P.R[:, 0, :]
    sp = np.zeros(len(w))
    sp[1:] = np.linalg.norm(np.diff(w, axis=0), axis=1)
    sp = np.convolve(sp, np.ones(3) / 3, mode="same")
    a, b = trim_edges(P, a, b, min_len)
    while b - a > min_len and sp[a] > V_TRAVEL:
        a += 1
    while b - a > min_len and sp[b - 1] > V_TRAVEL:
        b -= 1
    return a, b


def _motion(P: "Prepared", a: int, b: int) -> float:
    """Articulation over [a, b): summed mean landmark displacement of both hands (signing units)."""
    if b - a < 2:
        return 0.0
    H = np.concatenate([P.R[a:b], P.L[a:b]], axis=1)          # (n, 42, 2)
    return float(np.linalg.norm(np.diff(H, axis=0), axis=2).mean(axis=1).sum())


def is_active(o: Obs) -> bool:
    for H in (o.R, o.L):
        if H is not None and H[0, 1] < ACTIVE_Y and -10 < H[0, 0] < 110:
            return True
    return False


class PhraseTracker:
    def __init__(self):
        self.buf: list[Obs] = []
        self.pre: list[Obs] = []
        self.active_run = 0
        self.last_active_t: Optional[float] = None
        self.in_phrase = False

    def push(self, o: Obs) -> Optional[list[Obs]]:
        """Returns the finished phrase's frames when a phrase closes."""
        act = is_active(o)
        if not self.in_phrase:
            # pre-roll: only the last few frames, and never frames from before a pause in the stream
            self.pre = [f for f in self.pre if o.t - f.t <= 400][-(PREROLL + START_FRAMES - 1):] + [o]
            self.active_run = self.active_run + 1 if act else 0
            if self.active_run >= START_FRAMES:
                self.in_phrase = True
                self.buf = list(self.pre)
                self.last_active_t = o.t
            return None
        self.buf.append(o)
        self.recent = (getattr(self, "recent", []) + [act])[-3:]
        if sum(self.recent) >= 2:          # sustained activity only: a jittery hand at rest doesn't hold the phrase open
            self.last_active_t = o.t
        too_long = o.t - self.buf[0].t > MAX_PHRASE_MS
        lost = o.hands_present == 0
        limit = END_MS_LOST if lost else END_MS
        if (o.t - self.last_active_t) >= limit or too_long:
            return self.flush()
        return None

    def flush(self) -> Optional[list[Obs]]:
        if not self.in_phrase:
            return None
        frames = self.buf
        # trim the idle tail, keep two frames
        last = max((i for i, f in enumerate(frames) if is_active(f)), default=len(frames) - 1)
        frames = frames[: last + 3]
        self.buf, self.pre, self.active_run, self.in_phrase = [], [], 0, False
        self.recent = []
        return frames


# ------------------------------------------------------------------ preparation
@dataclass
class Prepared:
    t: np.ndarray                 # (N,)
    R: np.ndarray                 # (N,21,2)
    L: np.ndarray
    r_missing: np.ndarray         # bool (N,)
    l_missing: np.ndarray
    F: np.ndarray                 # (N, D) features (smoothed)
    overlap: np.ndarray           # (N,) hand bbox IoU (nan when one hand missing)
    active: np.ndarray            # bool (N,)
    noise: float = 0.0            # estimated landmark jitter, signing units


def _fill(arrs: list[Optional[np.ndarray]], rest: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = len(arrs)
    out = np.empty((n, 21, 2))
    missing = np.array([a is None for a in arrs])
    present = np.where(~missing)[0]
    for i in range(n):
        if not missing[i]:
            out[i] = arrs[i]
            continue
        before = present[present < i]
        after = present[present > i]
        b = before[-1] if len(before) else None
        a = after[0] if len(after) else None
        if b is not None and a is not None and (a - b) <= MAX_FILL + 1:
            w = (i - b) / (a - b)
            out[i] = arrs[b] * (1 - w) + arrs[a] * w
        elif b is not None and i - b <= 2:
            out[i] = arrs[b]
        elif a is not None and a - i <= 2:
            out[i] = arrs[a]
        else:
            out[i] = rest
    return out, missing


def prepare(frames: list[Obs]) -> Prepared:
    R, rm = _fill([f.R for f in frames], REST_R_LM)
    L, lm = _fill([f.L for f in frames], REST_L_LM)
    ov = np.array([bbox_iou(hand_bbox(f.R), hand_bbox(f.L)) if f.R is not None and f.L is not None else np.nan
                   for f in frames])
    present = ~rm
    noise = noise_level(R[present]) if present.sum() >= 6 else 0.0
    Rs, Ls = smooth_seq(R), smooth_seq(L)
    return Prepared(np.array([f.t for f in frames], dtype=float), Rs, Ls, rm, lm, features(Rs, Ls), ov,
                    np.array([is_active(f) for f in frames]), noise)


# ------------------------------------------------------------------ decoding
@dataclass
class Seg:
    a: int
    b: int                         # frame span [a, b)
    t0: float
    t1: float
    labels: list[tuple[str, float]]   # top-3 lattice
    probs: np.ndarray              # full distribution over index labels
    d_best: float
    kind: str                      # sign | letter | unknown
    disagreement: float = 0.0
    extra: dict = field(default_factory=dict)


def decode_phrase(P: Prepared, index: Index, tau: Optional[float] = None) -> list[Seg]:
    N = len(P.t)
    if N < 3:
        return []
    dt = float(np.median(np.diff(P.t))) if N > 1 else 33.3
    step = 2 if N <= 120 else 3
    pos = list(range(0, N, step))
    if pos[-1] != N:
        pos.append(N)
    idx = {p: i for i, p in enumerate(pos)}
    nu = noise_floor(P.noise)
    GAP_D = nu + GAP_BASE
    NOVEL_D = nu + NOVEL_BASE

    cand = []
    for i, a in enumerate(pos):
        for b in pos[i + 1:]:
            dur = P.t[min(b, N) - 1] - P.t[a] + dt
            if dur > SEG_MAX_MS:
                break
            if dur >= SEG_MIN_MS and P.active[a:b].mean() >= 0.5:
                cand.append((a, b, dur))
    if not cand:
        return []
    starts = np.array([c[0] for c in cand])
    ends = np.array([c[1] for c in cand])
    durs = np.array([c[2] for c in cand])
    Q = resample_batch(P.F, starts, ends, K)
    LD = index.label_distances(Q, durs)                 # (S, n_labels)
    best_l = LD.argmin(axis=1)
    best_d = LD[np.arange(len(cand)), best_l]
    seg_cost = {(a, b): (best_d[s] * (b - a) + SEG_PEN, s) for s, (a, b, _) in enumerate(cand)}

    INF = float("inf")
    dp = [INF] * len(pos)
    back: list[Optional[tuple]] = [None] * len(pos)
    dp[0] = 0.0
    for i, a in enumerate(pos):
        if dp[i] == INF:
            continue
        for b in pos[i + 1:]:
            j = idx[b]
            gdur = P.t[min(b, N) - 1] - P.t[a] + dt
            edge = (a == 0) != (b == N)          # leading OR trailing idle, not the whole phrase
            if edge or gdur <= GAP_MAX_MS:
                c = dp[i] + GAP_D * (b - a)
                if c < dp[j]:
                    dp[j], back[j] = c, ("gap", i, None)
            sc = seg_cost.get((a, b))
            if sc is not None:
                c = dp[i] + sc[0]
                if c < dp[j]:
                    dp[j], back[j] = c, ("seg", i, sc[1])
            if gdur > max(GAP_MAX_MS, SEG_MAX_MS) and not edge:
                break
    path = []                                   # ("seg", s) | ("gap", a, b)
    j = len(pos) - 1
    while j > 0 and back[j] is not None:
        kind, i, s = back[j]
        path.append(("seg", s) if kind == "seg" else ("gap", pos[i], pos[j]))
        j = i
    path.reverse()
    # merge consecutive gaps; long *moving* gaps are signs we don't know
    spans = []
    for p in path:
        if p[0] == "gap" and spans and spans[-1][0] == "gap":
            spans[-1] = ("gap", spans[-1][1], p[2])
        else:
            spans.append(p)
    segs_idx = []
    for k_, p in enumerate(spans):
        if p[0] == "seg":
            segs_idx.append(p[1])
            continue
        a, b = p[1], p[2]
        while a < b and not P.active[a]:
            a += 1
        while b > a and not P.active[b - 1]:
            b -= 1
        if b - a >= 3:
            a, b = trim_travel(P, a, b, min_len=3)
        dur = (P.t[b - 1] - P.t[a] + dt) if b > a else 0
        if dur >= UNKNOWN_MIN_MS and _motion(P, a, b) > UNKNOWN_MIN_MOTION:
            cand.append((a, b, dur))
            Qx = resample_batch(P.F, np.array([a]), np.array([b]), K)
            LDx = index.label_distances(Qx, np.array([dur]))
            best_d = np.append(best_d, LDx.min())
            Q = np.concatenate([Q, Qx])
            segs_idx.append(len(cand) - 1)
    if not segs_idx:
        return []

    # ensemble: every chosen span re-read at -2 / 0 / +2 frame offsets (section 04), one batch
    rows, owners = [], []
    for s in segs_idx:
        a, b, dur = cand[s]
        for d in (-2, 0, 2):
            x, y = max(0, a + d), min(N, b + d)
            if y - x >= 3:
                rows.append((x, y, dur)); owners.append(s)
    Qs = resample_batch(P.F, np.array([r[0] for r in rows]), np.array([r[1] for r in rows]), K)
    LDs = index.label_distances(Qs, np.array([r[2] for r in rows]))
    Ps_all = index.probs(LDs, tau) if tau else index.probs(LDs)
    owners = np.array(owners)
    eps = 1e-6
    out = []
    for s in segs_idx:
        a, b, dur = cand[s]
        Ps = Ps_all[owners == s]
        p = Ps.mean(axis=0)
        kls = []
        for u in range(len(Ps)):
            for v in range(u + 1, len(Ps)):
                pu, pv = Ps[u] + eps, Ps[v] + eps
                kls.append(0.5 * (np.sum(pu * np.log(pu / pv)) + np.sum(pv * np.log(pv / pu))))
        dis = float(np.mean(kls)) if kls else 0.0
        order = np.argsort(-p)[:3]
        labels = [(index.labels[i], float(p[i])) for i in order]
        d_best = float(best_d[s])
        kind = index.kind_of[labels[0][0]]
        if d_best > NOVEL_D:
            kind = "unknown"
        out.append(Seg(a, b, float(P.t[a]), float(P.t[b - 1]), labels, p, d_best, kind, dis,
                       {"Q": Q[s], "dur": dur, "novel_d": NOVEL_D, "noise": P.noise, "F": P.F[a:b]}))
    return out
