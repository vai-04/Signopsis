"""Fit the recognizer temperature and report the section-12 metrics for the avatar.

    python -m signopsis.eval.calibrate            # prints report, writes eval/report.json
    python -m signopsis.eval.calibrate --plot     # also writes eval/reliability.png (needs matplotlib)

Simulates perception at several noise levels (the real system gets these
from recorded clips). Metrics:
  - round-trip intelligibility: % of lexicon signs read back as themselves
  - ECE (expected calibration error) of the top-1 confidence
  - confidently-wrong rate: wrong reads among those that would have been emitted

Why the default TAU (0.08) is softer than the NLL fit: this synthetic set is
dominated by easy reads, so NLL favours a very sharp softmax, which makes the
rare near-duplicate pair (WATER/RIVER) confidently wrong. The gate prefers a
conservative temperature. Refit on real recorded clips before trusting either.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from signopsis.generate import roundtrip as RT
from signopsis.generate.avatar2d import render_offline
from signopsis.generate.signs import LEXICON
from signopsis.schemas import GlossItem, SignTarget

NOISES = (0.3, 0.8, 1.5, 2.5, 3.5)
REPS = 4


def collect(seed: int = 0):
    """Return distance matrix rows + labels for noisy reads of every sign."""
    rng = np.random.default_rng(seed)
    bank = RT.template_bank("sign")
    rows, truth, noise = [], [], []
    for g in bank.labels:
        t, R, L, _, segs = render_offline(SignTarget(gloss=[GlossItem(g=g, dur_ms=LEXICON[g]["dur"])]))
        s = segs[0]
        m = (t >= s.start - RT.SEG_SLOP_MS) & (t <= s.end + RT.SEG_SLOP_MS)
        for sd in NOISES:
            for _ in range(REPS):
                q = RT.resample(RT.features(R[m] + rng.normal(0, sd, R[m].shape),
                                            L[m] + rng.normal(0, sd, L[m].shape)))
                rows.append(RT.dtw_batch(q, bank.T))
                truth.append(bank.labels.index(g))
                noise.append(sd)
    return np.array(rows), np.array(truth), np.array(noise), bank.labels


def probs(D, tau):
    z = -D / tau
    z -= z.max(1, keepdims=True)
    p = np.exp(z)
    return p / p.sum(1, keepdims=True)


def fit_tau(D, y):
    grid = np.geomspace(0.001, 1.0, 80)
    nll = [-np.mean(np.log(probs(D, t)[np.arange(len(y)), y] + 1e-12)) for t in grid]
    return float(grid[int(np.argmin(nll))])


def ece(conf, correct, bins=10):
    edges = np.linspace(0, 1, bins + 1)
    e, table = 0.0, []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            e += m.mean() * abs(conf[m].mean() - correct[m].mean())
            table.append((float(conf[m].mean()), float(correct[m].mean()), int(m.sum())))
    return float(e), table


def main(plot: bool = False):
    D, y, noise, labels = collect()
    tau = fit_tau(D, y)
    low = noise <= 0.8
    report = {"fitted_tau": round(tau, 4), "current_tau": RT.TAU, "at": {}}
    table = []
    for name, t in (("current", RT.TAU), ("fitted", tau)):
        P = probs(D, t)
        top = P.argmax(1)
        conf = P.max(1)
        correct = (top == y).astype(float)
        e, tbl = ece(conf, correct)
        emitted = conf >= RT.THRESHOLD
        report["at"][name] = {
            "tau": round(t, 4),
            "ece": round(e, 4),
            "confidently_wrong_rate": round(float(1 - correct[emitted].mean()), 4) if emitted.any() else None,
            "emit_rate": round(float(emitted.mean()), 3),
            "reliability_bins": [[round(a, 3), round(b, 3), n] for a, b, n in tbl],
        }
        if name == "current":
            table, e_cur = tbl, e
            report["roundtrip_intelligibility_low_noise"] = round(float(correct[low].mean()), 3)
            report["accuracy_all_noise"] = round(float(correct.mean()), 3)
            report["naive_argmax_wrong_rate"] = round(float(1 - correct.mean()), 4)
            report["most_confused"] = sorted({f"{labels[a]}->{labels[b]}" for a, b in zip(y, top) if a != b})
    e = e_cur
    out = Path(__file__).parent / "report.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=1))
    if plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        xs = [c for c, _, _ in table]
        ys = [a for _, a, _ in table]
        fig, ax = plt.subplots(figsize=(4, 4))
        ax.plot([0, 1], [0, 1], "--", color="#999")
        ax.plot(xs, ys, "o-", color="#2a6f97")
        ax.set_xlabel("predicted confidence")
        ax.set_ylabel("observed accuracy")
        ax.set_title(f"Round-trip reliability (ECE {e:.3f})")
        fig.tight_layout()
        fig.savefig(Path(__file__).parent / "reliability.png", dpi=130)
    return report


if __name__ == "__main__":
    main(plot="--plot" in sys.argv)
