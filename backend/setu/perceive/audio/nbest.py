"""N-best hypotheses -> word lattice (a small confusion network).

Alternatives are aligned to the best hypothesis word-by-word. A slot's
candidate score is the posterior mass of the hypotheses that put that word
there. Word-level confidences from the decoder cap the top score, so an
N-best list that is suspiciously peaked still yields an honest margin.
Scores are uncalibrated until Phase 3 fits a temperature.
"""

from __future__ import annotations

import math
import re
from difflib import SequenceMatcher

from ...schemas import Candidate, LatticeSlot
from .base import Hypothesis

_PUNCT = re.compile(r"[^\w']+")


def _norm(w: str) -> str:
    return _PUNCT.sub("", w.lower())


def posteriors(scores: list[float], temperature: float = 1.0) -> list[float]:
    if not scores:
        return []
    m = max(scores)
    ex = [math.exp((s - m) / temperature) for s in scores]
    z = sum(ex)
    return [e / z for e in ex]


def hyps_to_lattice(hyps: list[Hypothesis], offset_ms: int = 0, temperature: float = 1.0,
                    max_cands: int = 4) -> list[LatticeSlot]:
    if not hyps or not hyps[0].words:
        return []
    best = hyps[0].words
    post = posteriors([h.score for h in hyps], temperature)
    votes: list[dict[str, float]] = [dict() for _ in best]
    display: list[dict[str, str]] = [dict() for _ in best]
    best_norm = [_norm(w.text) for w in best]

    def vote(i: int, text: str, mass: float) -> None:
        key = _norm(text)
        votes[i][key] = votes[i].get(key, 0.0) + mass
        display[i].setdefault(key, text)

    for i, w in enumerate(best):
        display[i][best_norm[i]] = w.text

    for h, mass in zip(hyps, post):
        alt = [w.text for w in h.words]
        sm = SequenceMatcher(a=best_norm, b=[_norm(t) for t in alt], autojunk=False)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == "equal":
                for k in range(i2 - i1):
                    vote(i1 + k, best[i1 + k].text, mass)
            elif op == "replace" and (i2 - i1) == (j2 - j1):
                for k in range(i2 - i1):
                    vote(i1 + k, alt[j1 + k], mass)
            elif op == "replace":
                vote(i1, " ".join(alt[j1:j2]), mass)
                for k in range(i1 + 1, i2):
                    vote(k, "", mass)
            elif op == "delete":
                for k in range(i1, i2):
                    vote(k, "", mass)
            # "insert": extra words in the alternative have no slot; ignored.

    slots: list[LatticeSlot] = []
    for i, w in enumerate(best):
        cands = sorted(votes[i].items(), key=lambda kv: kv[1], reverse=True)
        top_key = best_norm[i]
        top_mass = votes[i].get(top_key, 0.0)
        others = [(k, v) for k, v in cands if k != top_key]
        # Decoder less sure than the beam implies: shrink the top score. The freed
        # mass stays unassigned and counts as an unseen rival in slot_margin().
        top_score = min(top_mass, w.conf) if w.conf is not None else top_mass
        out = [Candidate(value=w.text, score=round(top_score, 4))]
        out += [Candidate(value=display[i][k], score=round(v, 4)) for k, v in others]
        out.sort(key=lambda c: c.score, reverse=True)
        slots.append(LatticeSlot(slot=i, cands=out[:max_cands],
                                 t0=offset_ms + w.start_ms, t1=offset_ms + w.end_ms))
    return slots
