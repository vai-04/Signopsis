"""SIGNOPSIS data contracts. These are the architecture: every stage reads/writes these.

Only the pieces needed by pipeline D (text -> sign) are fully specified here;
PerceptEvent is included so the sign->text team composes with the same types.
"""
from __future__ import annotations

import time
import uuid
from typing import Literal, Optional

from pydantic import BaseModel, Field


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def now_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------- PerceptEvent
class LatticeSlot(BaseModel):
    slot: int
    cands: list[tuple[str, float]]  # N-best, sorted desc

    def top1(self) -> tuple[str, float]:
        return self.cands[0]

    @property
    def margin(self) -> float:
        if len(self.cands) < 2:
            return self.cands[0][1]
        return self.cands[0][1] - self.cands[1][1]


class NonManual(BaseModel):
    brow: Literal["neutral", "raised", "furrowed"] = "neutral"
    head: Literal["neutral", "nod", "shake", "tilt_fwd"] = "neutral"
    mouth: Literal["neutral", "puffed", "pursed", "open"] = "neutral"
    eyegaze: str = "addressee"
    conf: float = 1.0


class PerceptEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("pe"))
    t0: int
    t1: int
    channel: Literal["sign", "speech", "screen", "text"]
    source: str
    lang_hint: str
    lattice: list[LatticeSlot]
    nonmanual: Optional[NonManual] = None
    quality: dict[str, float] = {}
    trust: Optional[float] = None
    partial: bool = False


# --------------------------------------------------------------- SemanticFrame
class Entity(BaseModel):
    text: str
    type: str = "thing"
    resolved_from: Literal["lexicon", "lattice", "context", "user", "fingerspell"] = "lexicon"
    alternatives: list[str] = []
    margin: float = 1.0


class Prosody(BaseModel):
    affect: Literal["neutral", "happy", "sad", "urgent", "angry"] = "neutral"
    intensity: float = 0.3
    emphasis: list[str] = []
    pace: Literal["slow", "normal", "fast"] = "normal"
    conf: float = 0.8


class Grounding(BaseModel):
    span: tuple[int, int]            # char span in source text
    percept_ids: list[str]
    t: tuple[int, int] = (0, 0)
    gloss_index: Optional[int] = None  # which output gloss this span produced


class Unresolved(BaseModel):
    slot: int                         # index into the gloss sequence
    cands: list[str]
    reason: Literal["low_margin", "lexical_ambiguity", "unknown_word", "roundtrip_fail"]
    source_text: str = ""
    token_index: int = -1             # key to send back in a repair resolution


class Provenance(BaseModel):
    resolver: str = "rules-isl-v1"
    escalated_to_cloud: bool = False


class SemanticFrame(BaseModel):
    id: str = Field(default_factory=lambda: new_id("sf"))
    utterance: str
    lang: str
    speech_act: Literal["statement", "question", "request", "correction", "backchannel"]
    question_type: Optional[Literal["wh", "yesno"]] = None
    negated: bool = False
    entities: list[Entity] = []
    prosody: Prosody = Prosody()
    grounding: list[Grounding] = []
    unresolved: list[Unresolved] = []
    gloss: list[str] = []             # resolver's ISL gloss (pre-render)
    high_stakes: bool = False
    trust: float = 1.0
    provenance: Provenance = Provenance()


# ------------------------------------------------------------------ RenderPlan
class GlossItem(BaseModel):
    g: str
    dur_ms: int
    fs_fallback: Optional[str] = None   # letters to spell if sign can't be trusted
    fingerspelled: bool = False         # True -> renderer spells fs_fallback instead of signing
    conf: float = 1.0
    roundtrip: Optional[float] = None   # per-gloss read-back probability
    source_span: Optional[tuple[int, int]] = None


class NMKey(BaseModel):
    t: int
    brow: Optional[str] = None
    head: Optional[str] = None
    mouth: Optional[str] = None


class CaptionTarget(BaseModel):
    kind: Literal["caption"] = "caption"
    lang: str
    text: str
    trust_badge: Literal["high", "medium", "low"]
    forced: bool = False                # caption forced on because a sign degraded
    speaker_label: str = "You"


class SignTarget(BaseModel):
    kind: Literal["sign"] = "sign"
    sign_lang: Literal["isl", "asl"] = "isl"
    gloss: list[GlossItem]
    nonmanual: list[NMKey] = []
    affect: str = "neutral"
    roundtrip_score: float = 0.0
    back_translation: str = ""          # author preview (pipeline D closed loop)
    total_ms: int = 0


class RepairOption(BaseModel):
    gloss: str
    label: str
    clip: Optional[str] = None


class Repair(BaseModel):
    type: Literal["disambiguate", "confirm", "resign", "teach"]
    slot: int                           # gloss slot in question (-1 = whole utterance)
    token_index: int = -1               # send back as {token_index: gloss} to resolve
    prompt: str
    options: list[RepairOption]


class TTSTarget(BaseModel):
    kind: Literal["tts"] = "tts"
    engine: str = "browser-speech"      # swap for "kokoro-82m" on the GPU box
    lang: str = "en"
    text: str
    voice: str = "default"
    emphasis: list[str] = []
    rate: float = 1.0
    pitch: float = 1.0
    volume: float = 1.0


class RenderPlan(BaseModel):
    frame_id: str
    gate: Literal["emit", "repair", "hold"]
    gate_reason: str = ""
    targets: list[CaptionTarget | SignTarget | TTSTarget]
    repair: Optional[Repair] = None
    advisory: Optional[str] = None      # high-stakes banner
    timings_ms: dict[str, float] = {}

    def sign(self) -> SignTarget:
        return next(t for t in self.targets if isinstance(t, SignTarget))

    def caption(self) -> CaptionTarget:
        return next(t for t in self.targets if isinstance(t, CaptionTarget))


# ------------------------------------------------------------ wire contract (L0)
class WireHand(BaseModel):
    lm: list[list[float]]               # 21 x [x, y, z], image-normalized, UNMIRRORED
    label: str = ""                     # MediaPipe handedness label (assumes mirrored input)
    score: float = 1.0


class WireFace(BaseModel):
    bs: dict[str, float] = {}           # MediaPipe face blendshapes (subset)
    nose: Optional[list[float]] = None  # [x, y] image-normalized


class WireFrame(BaseModel):
    """What a camera client sends per video frame. Raw pixels never leave the device."""
    type: Literal["frame"] = "frame"
    t: float                            # ms, client monotonic clock
    w: int = 640
    h: int = 480
    hands: list[WireHand] = []
    pose: Optional[list[list[float]]] = None   # >= 17 x [x, y, z, visibility]
    face: Optional[WireFace] = None
    lux: Optional[float] = None         # mean luma 0..255 from a tiny downscaled frame
    mirrored: bool = False              # True if the landmarks came from a mirrored image
