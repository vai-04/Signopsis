"""Synthetic lattices so the gate, WebSocket and UI work before any model exists.

`FakeASR` cycles through three scripted utterances, one per gate:
emit (confident), repair (a their/there homophone), hold (mumbled).
"""

from __future__ import annotations

import numpy as np

from ..schemas import Candidate, LatticeSlot, PerceptEvent, Quality
from .audio.base import ASRResult, Hypothesis, Word

SCRIPT = [
    # (words, per-word alternatives {index: [(alt, score)]}, top score, snr_db)
    ("Good morning, the meeting starts at ten.".split(), {}, 0.97, 25.0),
    ("I left my notes over their by the window.".split(), {5: [("there", 0.44)]}, 0.52, 22.0),
    ("mm the uh maybe".split(), {1: [("a", 0.33)], 3: [("baby", 0.30)]}, 0.35, 4.0),
]


def fake_lattice(kind: int, t0: int = 0, word_ms: int = 300) -> list[LatticeSlot]:
    words, alts, top, _ = SCRIPT[kind % len(SCRIPT)]
    slots = []
    for i, w in enumerate(words):
        score = top if i in alts or kind == 2 else 0.98
        cands = [Candidate(value=w, score=score)] + [Candidate(value=a, score=s) for a, s in alts.get(i, [])]
        slots.append(LatticeSlot(slot=i, cands=cands, t0=t0 + i * word_ms, t1=t0 + (i + 1) * word_ms))
    return slots


def fake_percept(kind: int, t0: int = 0) -> PerceptEvent:
    lattice = fake_lattice(kind, t0)
    snr = SCRIPT[kind % len(SCRIPT)][3]
    return PerceptEvent(t0=t0, t1=lattice[-1].t1 or t0, channel="speech", source="fake",
                        lang_hint="en", lattice=lattice, quality=Quality(snr_db=snr))


class FakeASR:
    """Drop-in ASREngine: ignores audio content, returns scripted lattices."""

    name = "fake"

    def __init__(self) -> None:
        self._next = 0

    def load(self) -> None:
        pass

    def warmup(self) -> None:
        pass

    def transcribe_partial(self, audio: np.ndarray) -> str:
        words = SCRIPT[self._next % len(SCRIPT)][0]
        n = max(1, min(len(words), int(len(audio) / 16000 / 0.3)))
        return " ".join(words[:n])

    def transcribe_final(self, audio: np.ndarray) -> ASRResult:
        kind = self._next
        self._next += 1
        words, alts, top, snr = SCRIPT[kind % len(SCRIPT)]
        best = Hypothesis([Word(w, i * 300, (i + 1) * 300, conf=top if (i in alts or kind % 3 == 2) else 0.98)
                           for i, w in enumerate(words)], score=0.0)
        hyps = [best]
        for i, rivals in alts.items():
            for alt, s in rivals:
                ws = [Word(w.text, w.start_ms, w.end_ms, w.conf) for w in best.words]
                ws[i].text = alt
                hyps.append(Hypothesis(ws, score=float(np.log(s / top))))
        return ASRResult(hyps=hyps, lang="en", source="fake", extra={"snr_db": snr})
