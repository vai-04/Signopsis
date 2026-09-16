"""Diarizer interface + speaker binding rule (Section 6C).

A label is bound only after 2 consecutive diarizer chunks agree on the
dominant speaker; otherwise the caption carries no speaker label.
"""

from __future__ import annotations

import numpy as np

FRAME_MS = 80                      # Sortformer output resolution
BIND_CHUNK_FRAMES = 4              # 320 ms decision chunks
ACTIVE_PROB = 0.35


class NullDiarizer:
    frame_ms = FRAME_MS

    def push(self, audio: np.ndarray) -> None:
        pass

    def processed_until(self) -> int:
        return 1 << 62

    def probs(self, start_sample: int, end_sample: int) -> np.ndarray:
        return np.zeros((0, 4), dtype=np.float32)


def bind_speaker(probs: np.ndarray, chunk: int = BIND_CHUNK_FRAMES) -> tuple[int | None, float]:
    """probs: (T, S) speaker activity. Returns (speaker index | None, confidence)."""
    t = len(probs)
    if t < 2:
        return None, 0.0
    chunk = max(1, min(chunk, t // 2))
    decisions: list[int | None] = []
    for i in range(0, t - chunk + 1, chunk):
        mean = probs[i:i + chunk].mean(axis=0)
        k = int(mean.argmax())
        decisions.append(k if mean[k] >= ACTIVE_PROB else None)

    agreed = {d for a, d in zip(decisions, decisions[1:]) if d is not None and a == d}
    if not agreed:
        return None, 0.0
    mass = probs.sum(axis=0)
    best = max(agreed, key=lambda k: mass[k])
    col = probs[:, best]
    active = col[col >= ACTIVE_PROB]
    return best, float(active.mean() if len(active) else col.mean())
