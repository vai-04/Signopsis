"""PerceptEvent — what every L1 perceiver emits (Section 4.1)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from ulid import ULID

Channel = Literal["sign", "speech", "screen", "text"]   # "text" = typed input (Compose, S11)


def new_id(prefix: str) -> str:
    return f"{prefix}_{ULID()}"


class Candidate(BaseModel):
    value: str
    score: float                      # calibrated probability after L2


class LatticeSlot(BaseModel):
    slot: int
    cands: list[Candidate]            # N-best, sorted desc
    # Optional extension: slot timing on the session clock (used for grounding).
    t0: int | None = None
    t1: int | None = None


class NonManual(BaseModel):
    brow: Literal["neutral", "raised", "furrowed"] = "neutral"
    head: Literal["neutral", "tilt_fwd", "tilt_side", "nod", "shake"] = "neutral"
    mouth: str = "neutral"
    eyegaze: str = "addressee"
    conf: float = 0.0


class Speaker(BaseModel):
    id: str
    conf: float
    modality: Literal["audio", "visual", "audio+visual"]


class Quality(BaseModel):
    landmark_vis: float | None = None
    hand_overlap: float | None = None
    motion_blur: float | None = None
    snr_db: float | None = None
    lux_est: float | None = None


class PerceptEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("pe"))
    t0: int                           # ms, session clock
    t1: int
    channel: Channel
    source: str                       # "parakeet-tdt" | "faster-whisper" | "fake" | ...
    lang_hint: str                    # "isl" | "asl" | "en" | "hi" | "ta"
    lattice: list[LatticeSlot]
    nonmanual: NonManual | None = None
    speaker: Speaker | None = None
    quality: Quality = Field(default_factory=Quality)
    prosody_raw: dict | None = None   # pitch, energy, rate, emotion probs
    trust: float | None = None        # filled by L2 only
    partial: bool = False

    def top1(self) -> list[str]:
        return [s.cands[0].value for s in self.lattice if s.cands]
