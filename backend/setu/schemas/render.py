"""RenderPlan — what L4 hands to captions / TTS / avatar (Section 4.3)."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

Gate = Literal["emit", "repair", "hold"]


class CaptionTarget(BaseModel):
    kind: Literal["caption"] = "caption"
    lang: str
    text: str
    trust_badge: Literal["high", "medium", "low", "enhanced"]
    speaker_label: str | None = None
    uncertain_spans: list[tuple[int, int]] = []
    forced: bool = False              # shown even for signing users: a sign fell back to fingerspelling


class TTSTarget(BaseModel):
    kind: Literal["tts"] = "tts"
    engine: str = "kokoro-82m"
    voice: str
    emphasis: list[str] = []
    rate: float = 1.0


class GlossToken(BaseModel):
    g: str                            # ISL gloss; "FS:WORD" = a word with no sign
    dur_ms: int
    fs_fallback: str | None = None    # letters "P-R-I-Y-A" to spell if the sign can't be trusted
    conf: float | None = None
    fingerspelled: bool = False       # True -> renderer spells fs_fallback instead of signing
    roundtrip: float | None = None    # per-gloss read-back probability (round-trip gate)
    source_span: tuple[int, int] | None = None   # char span in the source text


class NMKey(BaseModel):
    """Non-manual keyframe on the signing timeline (ms from plan start)."""

    t: int
    brow: str | None = None
    head: str | None = None
    mouth: str | None = None


class SignTarget(BaseModel):
    kind: Literal["sign"] = "sign"
    sign_lang: Literal["isl", "asl"] = "isl"
    gloss: list[GlossToken]
    nonmanual: list[NMKey] = []
    affect: str = "neutral"
    roundtrip_score: float | None = None
    back_translation: str | None = None   # what the recognizer read back, in words
    total_ms: int = 0


Target = Annotated[Union[CaptionTarget, TTSTarget, SignTarget], Field(discriminator="kind")]


class RepairOption(BaseModel):
    gloss_or_word: str
    score: float
    clip: str | None = None
    label: str | None = None          # plain-language label for the button


class Repair(BaseModel):
    type: Literal["disambiguate", "hold", "teach", "homophone", "confirm"]
    reason: str                       # human-readable, specific
    options: list[RepairOption] = []
    slot: int | None = None           # gloss/word slot in question (None = whole utterance)
    token_index: int | None = None    # sign path: send back as {token_index: gloss} to resolve


class RenderPlan(BaseModel):
    frame_id: str
    gate: Gate
    targets: list[Target]
    repair: Repair | None = None
    back_translation: str | None = None   # for Compose (S11)
    gate_reason: str | None = None        # why the gate decided this (S11 / diagnostics)
    advisory: str | None = None           # high-stakes banner text
    timings_ms: dict[str, float] = {}
