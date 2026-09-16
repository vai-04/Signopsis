"""Terminal harness for the live sign -> text layer (no webcam, no browser).

    python -m signopsis.perceive.simulate "I went to the bank yesterday."
    python -m signopsis.perceive.simulate "My mother is sick" --severity 0.8 --seed 3
    python -m signopsis.perceive.simulate --gloss ME,RIVER,GO --answer RIVER        # repair flow
    python -m signopsis.perceive.simulate --gloss MY,NAME,DEMO-NAMESIGN              # unknown sign -> hold
    python -m signopsis.perceive.simulate --teach Kushagra --gloss MY,NAME,DEMO-NAMESIGN   # teach, then use it
    python -m signopsis.perceive.simulate "What is your name?" --lang hi --lefty
"""
from __future__ import annotations

import argparse
import json

import numpy as np

from signopsis.memory.store import MemoryStore
from signopsis.perceive.session import SignSession
from signopsis.perceive.simcam import Degrade, plan_for, stream, text_stream


def show(e: dict, verbose: bool):
    p = e["plan"]
    print(f"  [{p['gate'].upper():6}] {e['text'] or '(nothing shown)'}")
    print(f"           {p['gate_reason']}")
    for s in e["slots"]:
        print(f"           - {s['display']:<12} {s['kind']:<8} trust {s['trust']:.2f}  source {s['source']:<8}"
              f" seen {', '.join(f'{g}:{q:.2f}' for g, q in s['visual'][:2])}")
    if p.get("repair"):
        r = p["repair"]
        print(f"           repair ({r['type']}): {r['prompt']} -> " + " | ".join(o["label"] for o in r["options"]))
    if p.get("advisory"):
        print(f"           ! {p['advisory']}")
    print(f"           timings {p['timings_ms']}  coverage {e['percept']['quality'].get('coverage') if e.get('percept') else '-'}")
    if verbose:
        print(json.dumps({"frame": e["frame"], "plan": p}, indent=1, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?", default="")
    ap.add_argument("--gloss", default="", help="comma-separated glosses instead of text (e.g. ME,RIVER,GO)")
    ap.add_argument("--severity", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--lefty", action="store_true")
    ap.add_argument("--lang", default="en", choices=["en", "hi"])
    ap.add_argument("--user", default="sim")
    ap.add_argument("--answer", default="", help="auto-answer a disambiguation with this gloss")
    ap.add_argument("--teach", default="", help="teach a sign under this label first (4 samples)")
    ap.add_argument("--teach-gloss", default="DEMO-NAMESIGN", help="which motion to teach (default: an unlisted demo sign)")
    ap.add_argument("--data", default="", help="memory directory (default: SIGNOPSIS_DATA or ./data)")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    store = MemoryStore(a.data) if a.data else MemoryStore()
    sess = SignSession(a.user, store, out_lang=a.lang, dominant="left" if a.lefty else "right")
    rng = np.random.default_rng(a.seed)
    t0 = 0.0

    def frames_for(seed, gloss=None):
        nonlocal t0
        deg = Degrade.random(np.random.default_rng(seed), a.severity) if a.severity > 0 else Degrade()
        deg.lefty = a.lefty
        gloss = gloss or a.gloss
        if gloss:
            fr = stream(plan_for([g.strip().upper() for g in gloss.split(",")]), deg, seed=seed, t0=t0)
        else:
            fr, _ = text_stream(a.text, deg, seed=seed, t0=t0)
        t0 = fr[-1]["t"] + 1000
        return fr

    def run(seed, gloss=None):
        out = []
        for f in frames_for(seed, gloss):
            out += sess.handle(f)
        return out + sess.handle({"type": "flush"})

    if a.teach:
        print(sess.handle({"type": "enroll_start", "label": a.teach})[0])
        for k in range(4):
            for e in run(a.seed + 100 + k, a.teach_gloss):
                if e["type"] in ("enroll_progress", "enrolled"):
                    print(" ", {x: e[x] for x in e if x in ("type", "label", "have", "need", "consistency", "warning")})

    print(f"signing: {a.gloss or a.text!r}  severity {a.severity}")
    for e in run(a.seed):
        if e["type"] == "result":
            show(e, a.verbose)
            rep = e["plan"].get("repair")
            if a.answer and rep and rep["type"] == "disambiguate":
                print(f"  answering {a.answer!r}")
                for e2 in sess.handle({"type": "repair_choice", "frame_id": e["plan"]["frame_id"],
                                       "slot": rep["slot"], "choice": a.answer}):
                    if e2["type"] == "result":
                        show(e2, a.verbose)
        elif e["type"] == "teach_offer":
            print("  teach offer:", e["prompt"])


if __name__ == "__main__":
    main()
