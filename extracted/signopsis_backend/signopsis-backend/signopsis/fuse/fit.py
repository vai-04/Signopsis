"""Fit L2 trust weights and report the section-12 metrics for sign -> text.

    python -m signopsis.fuse.fit                 # fit + write fuse/weights.json + eval/sign_report.json
    python -m signopsis.fuse.fit --eval-only     # evaluate the current weights
    python -m signopsis.fuse.fit --n 400 --plot  # bigger run, reliability diagram PNG

Data: simulated camera streams (signopsis.perceive.simcam) of random ISL
sentences under random degradation (studio -> awful). Replace with
recorded clips + labels when you have them; the fitting code is the same.

Labels: a slot is "correct" if it aligns (edit distance) to the same
gloss in the reference sequence.
"""
from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

import numpy as np

from signopsis.fuse.trust import DEFAULT, EMIT_AT, WEIGHTS_PATH, SlotSignals, TrustModel, sigmoid
from signopsis.memory.store import MemoryStore
from signopsis.perceive.session import SignSession
from signopsis.perceive.simcam import Degrade, plan_for, stream, text_stream
from signopsis.resolve import vocab as V
from signopsis.generate.signs import LEXICON

SENTENCES = [
    "I went to the bank yesterday.", "What is your name?", "Do you want water?", "I don't understand.",
    "My name is Priya.", "They went home", "Where is the toilet?", "I have pain, I need medicine.",
    "Hello, thank you", "My mother is sick", "Are you sick?", "Tomorrow I will go to school",
    "Where is the hospital?", "I need a doctor now", "Help me please", "What time is it?", "How are you?",
    "Who are you?", "I am happy", "She doesn't know", "We go home now", "I like books",
    "My friend is coming tomorrow", "Where do you work?", "My father is a doctor", "I want money",
    "How much money?", "You understand?", "I am not sick", "Good morning", "Sorry, I don't know",
    "Today I work", "Do you need help?", "I drink water", "My name is Ravi", "Thank you, doctor",
]
ORDER = ["TIME", "PRON", "NOUN", "ADJ", "VERB", "NEG", "WH"]


def random_gloss(rng) -> list[str]:
    by = {}
    for g, c in V.CATEGORY.items():
        if g in LEXICON:
            by.setdefault(c, []).append(g)
    out = []
    for c in ORDER:
        if c in by and rng.random() < {"TIME": .35, "PRON": .7, "NOUN": .6, "ADJ": .2, "VERB": .6, "NEG": .15, "WH": .2}[c]:
            out.append(str(rng.choice(by[c])))
    if not out:
        out = [str(rng.choice(by["NOUN"]))]
    if rng.random() < 0.15:
        out.insert(int(rng.integers(0, len(out) + 1)), "FS:" + str(rng.choice(["RAVI", "ANU", "DELHI", "MANGO", "PRIYA"])))
    if rng.random() < 0.2:      # oversample the planted near-duplicate pair so the fit sees real ambiguity
        pos = [i for i, g in enumerate(out) if V.CATEGORY.get(g) == "NOUN"]
        g = str(rng.choice(["WATER", "RIVER"]))
        if pos:
            out[pos[0]] = g
        else:
            out.insert(min(1, len(out)), g)
    return out


def align(pred: list[str], ref: list[str]) -> list[bool]:
    """Per predicted token: aligned to an identical reference token?"""
    n, m = len(pred), len(ref)
    D = np.zeros((n + 1, m + 1), dtype=int)
    D[:, 0] = np.arange(n + 1)
    D[0, :] = np.arange(m + 1)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            D[i, j] = min(D[i - 1, j] + 1, D[i, j - 1] + 1, D[i - 1, j - 1] + (pred[i - 1] != ref[j - 1]))
    ok = [False] * n
    i, j = n, m
    while i > 0 and j > 0:
        if D[i, j] == D[i - 1, j - 1] + (pred[i - 1] != ref[j - 1]):
            ok[i - 1] = pred[i - 1] == ref[j - 1]
            i, j = i - 1, j - 1
        elif D[i, j] == D[i - 1, j] + 1:
            i -= 1
        else:
            j -= 1
    return ok


def run_phrase(sess: SignSession, frames: list[dict]) -> list[dict]:
    sess.handle({"type": "reset"})
    res = []
    for f in frames:
        res += [e for e in sess.handle(f) if e["type"] == "result"]
    res += [e for e in sess.handle({"type": "flush"}) if e["type"] == "result"]
    return res


def collect(n: int, seed: int, weights=None, progress=True):
    rng = np.random.default_rng(seed)
    sess = SignSession("fit", MemoryStore(Path(tempfile.mkdtemp())), TrustModel(weights))
    rows, phrases = [], []
    t0 = time.time()
    for k in range(n):
        sev = float(rng.choice([0.0, 0.2, 0.4, 0.6, 0.8, 1.0]))
        deg = Degrade.random(rng, sev) if sev > 0 else Degrade(noise=float(rng.uniform(0.2, 0.6)))
        if rng.random() < 0.5:
            text = str(rng.choice(SENTENCES))
            frames, info = text_stream(text, deg, seed=int(rng.integers(1 << 30)))
            ref = info["signed"]
        else:
            ref = random_gloss(rng)
            frames = stream(plan_for(ref), deg, seed=int(rng.integers(1 << 30)))
            text = " ".join(ref)
        ref = [V.EN.get(g[3:].lower(), g) if g.startswith("FS:") else g for g in ref]
        sess.dominant = "left" if deg.lefty else "right"
        results = run_phrase(sess, frames)
        pred = []
        for r in results:
            pred += [s["gloss"] for s in r["slots"]]
        ok = align(pred, ref)
        j = 0
        for r in results:
            for s in r["slots"]:
                sig = s["signals"]
                rows.append({**sig, "ctx_margin": s["ctx_margin"], "correct": ok[j], "sev": sev,
                             "kind": s["kind"], "trust": s["trust"]})
                j += 1
        gates = [r["gate"] for r in results] or ["none"]
        covs = [r["percept"]["quality"].get("coverage", 1.0) for r in results if r.get("percept")]
        phrases.append({"ref": ref, "pred": pred, "sev": sev, "gates": gates, "coverage": min(covs) if covs else None,
                        "exact": pred == ref, "text": text,
                        "emitted_wrong": any(g == "emit" for g in gates) and pred != ref})
        if progress and (k + 1) % 50 == 0:
            print(f"  {k + 1}/{n} phrases  ({time.time() - t0:.0f}s)", flush=True)
    return rows, phrases


def logreg(X, y, l2=1e-2, iters=3000, lr=0.5):
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = (X - mu) / sd
    w = np.zeros(Z.shape[1])
    b = 0.0
    for _ in range(iters):
        p = sigmoid(Z @ w + b)
        g = p - y
        w -= lr * (Z.T @ g / len(y) + l2 * w)
        b -= lr * g.mean()
    # back to raw feature space
    return (w / sd).tolist(), float(b - np.sum(w * mu / sd))


def ece(conf, correct, bins=10):
    conf, correct = np.asarray(conf), np.asarray(correct, float)
    e, table = 0.0, []
    for lo, hi in zip(np.linspace(0, 1, bins + 1)[:-1], np.linspace(0, 1, bins + 1)[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            e += m.mean() * abs(conf[m].mean() - correct[m].mean())
            table.append([round(float(conf[m].mean()), 3), round(float(correct[m].mean()), 3), int(m.sum())])
    return float(e), table


def fit(rows) -> dict:
    sigs = [SlotSignals(**{k: r[k] for k in SlotSignals.__dataclass_fields__}) for r in rows]
    y = [r["correct"] for r in rows]
    qX = [s.quality_vec() for s in sigs]
    qw, qb = logreg(qX, y)
    W = {"quality": {"w": qw, "b": qb}, "trust": DEFAULT["trust"], "tau": DEFAULT["tau"], "fitted": True}
    tm = TrustModel(W)
    tX = [tm.trust_vec(s, margin=r["ctx_margin"]) for s, r in zip(sigs, rows)]
    tw, tb = logreg(tX, y)
    W["trust"] = {"w": tw, "b": tb}
    W["n_train"] = len(rows)
    return W


def evaluate(rows, phrases, W) -> dict:
    tm = TrustModel(W)
    sigs = [SlotSignals(**{k: r[k] for k in SlotSignals.__dataclass_fields__}) for r in rows]
    conf = np.array([tm.trust(s, margin=r["ctx_margin"]) for s, r in zip(sigs, rows)])
    y = np.array([r["correct"] for r in rows], float)
    e, table = ece(conf, y)
    emit = conf >= EMIT_AT
    sev = np.array([r["sev"] for r in rows])
    by_sev = {}
    for sv in sorted(set(sev)):
        m = sev == sv
        by_sev[str(sv)] = {"slots": int(m.sum()), "accuracy": round(float(y[m].mean()), 3),
                           "emit_rate": round(float(emit[m].mean()), 3),
                           "confidently_wrong": round(float(1 - y[m & emit].mean()), 4) if (m & emit).any() else None}
    ph_emit = [p for p in phrases if "emit" in p["gates"]]
    return {
        "slots": len(rows),
        "phrases": len(phrases),
        "slot_accuracy_top1": round(float(y.mean()), 4),
        "naive_argmax_wrong_rate": round(float(1 - y.mean()), 4),
        "confidently_wrong_rate": round(float(1 - y[emit].mean()), 4) if emit.any() else None,
        "slot_emit_rate": round(float(emit.mean()), 4),
        "ece": round(e, 4),
        "reliability_bins": table,
        "by_severity": by_sev,
        "phrase_exact_accuracy": round(float(np.mean([p["exact"] for p in phrases])), 4),
        "phrase_emit_rate": round(len(ph_emit) / max(len(phrases), 1), 4),
        "phrase_confidently_wrong_rate": round(float(np.mean([p["emitted_wrong"] for p in ph_emit])), 4) if ph_emit else None,
        "phrase_repair_rate": round(float(np.mean(["repair" in p["gates"] for p in phrases])), 4),
        "phrase_hold_rate": round(float(np.mean(["hold" in p["gates"] for p in phrases])), 4),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=240)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--eval-only", action="store_true")
    ap.add_argument("--plot", action="store_true")
    a = ap.parse_args()
    out_dir = Path(__file__).resolve().parents[1] / "eval"
    if not a.eval_only:
        print(f"collecting {a.n} training phrases ...")
        rows, _ = collect(a.n, a.seed, weights=DEFAULT)
        W = fit(rows)
        WEIGHTS_PATH.write_text(json.dumps(W, indent=2))
        print("wrote", WEIGHTS_PATH)
    W = json.loads(WEIGHTS_PATH.read_text()) if WEIGHTS_PATH.exists() else DEFAULT
    print(f"collecting {max(a.n // 2, 60)} held-out phrases ...")
    rows, phrases = collect(max(a.n // 2, 60), a.seed + 1000, weights=W)
    rep = evaluate(rows, phrases, W)
    (out_dir / "sign_report.json").write_text(json.dumps(rep, indent=2))
    print(json.dumps({k: v for k, v in rep.items() if k != "reliability_bins"}, indent=2))
    if a.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        xs = [b[0] for b in rep["reliability_bins"]]
        ys = [b[1] for b in rep["reliability_bins"]]
        fig, ax = plt.subplots(figsize=(4, 4))
        ax.plot([0, 1], [0, 1], "--", color="#999")
        ax.plot(xs, ys, "o-", color="#2a6f97")
        ax.set_xlabel("trust (predicted)")
        ax.set_ylabel("observed accuracy")
        ax.set_title(f"Sign→text trust reliability (ECE {rep['ece']:.3f})")
        fig.tight_layout()
        fig.savefig(out_dir / "sign_reliability.png", dpi=130)


if __name__ == "__main__":
    main()
