"""Shared types for audio perceivers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np


@dataclass
class Word:
    text: str
    start_ms: int                     # relative to the segment start
    end_ms: int
    conf: float | None = None


@dataclass
class Hypothesis:
    words: list[Word]
    score: float = 0.0                # log score from the decoder


@dataclass
class ASRResult:
    hyps: list[Hypothesis]            # best first
    lang: str
    source: str
    extra: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.hyps[0].words) if self.hyps else ""


class ASREngine(Protocol):
    name: str

    def load(self) -> None: ...
    def warmup(self) -> None: ...
    def transcribe_partial(self, audio: np.ndarray) -> str: ...
    def transcribe_final(self, audio: np.ndarray) -> ASRResult: ...


class VADModel(Protocol):
    def prob(self, frame: np.ndarray) -> float: ...
    def reset(self) -> None: ...


def pcm16_to_float(buf: bytes) -> np.ndarray:
    return np.frombuffer(buf, dtype="<i2").astype(np.float32) / 32768.0
