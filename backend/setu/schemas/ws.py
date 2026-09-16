"""WebSocket messages — discriminated union on `type` (Section 4.4)."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter

from .frame import SemanticFrame
from .percept import LatticeSlot, PerceptEvent
from .render import Gate, RenderPlan
from .session import AskWhenUnsure, Mode, SignLang

# ---------------------------------------------------------------- client -> server


class SessionStart(BaseModel):
    type: Literal["session.start"] = "session.start"
    mode: Mode = "LISTEN"
    sign_lang: SignLang = "isl"
    spoken_langs: list[str] = ["en"]
    role: str = "listener"
    ask_when_unsure: AskWhenUnsure = "balanced"
    sign_output: bool = True          # voice -> sign: emitted captions are also signed
    avatar_frames: bool = True        # include avatar landmark frames in render.plan


class AudioChunk(BaseModel):
    type: Literal["audio.chunk"] = "audio.chunk"
    seq: int
    pcm16_b64: str                    # mono, 16 kHz, little-endian int16
    t: int                            # client clock ms


class VideoFrame(BaseModel):
    type: Literal["video.frame"] = "video.frame"
    seq: int
    jpeg_b64: str
    t: int


class LandmarksMsg(BaseModel):
    type: Literal["landmarks"] = "landmarks"
    seq: int
    data: Any
    t: int


class BlendshapesMsg(BaseModel):
    type: Literal["blendshapes"] = "blendshapes"
    seq: int
    data: Any
    t: int


class SigningWindow(BaseModel):
    type: Literal["signing.window"] = "signing.window"
    state: Literal["open", "close"]


class RepairPick(BaseModel):
    type: Literal["repair.pick"] = "repair.pick"
    frame_id: str
    choice: str


class RepairNeither(BaseModel):
    type: Literal["repair.neither"] = "repair.neither"
    frame_id: str


class ComposeText(BaseModel):
    type: Literal["compose.text"] = "compose.text"
    text: str
    target_sign_lang: SignLang = "isl"
    resolutions: dict[int, str] = {}  # {token_index: gloss} answers to a sign repair


class VerbatimToggle(BaseModel):
    type: Literal["verbatim.toggle"] = "verbatim.toggle"
    on: bool


class ModeSet(BaseModel):
    type: Literal["mode.set"] = "mode.set"
    mode: Mode


class SessionEnd(BaseModel):
    type: Literal["session.end"] = "session.end"


ClientMessage = Annotated[
    Union[
        SessionStart, AudioChunk, VideoFrame, LandmarksMsg, BlendshapesMsg, SigningWindow,
        RepairPick, RepairNeither, ComposeText, VerbatimToggle, ModeSet, SessionEnd,
    ],
    Field(discriminator="type"),
]
client_message = TypeAdapter(ClientMessage)

# ---------------------------------------------------------------- server -> client


class SessionReady(BaseModel):
    type: Literal["session.ready"] = "session.ready"
    session_id: str
    asr: str
    diarizer: str
    vad: str
    trust_calibrated: bool


class CaptionPartial(BaseModel):
    type: Literal["caption.partial"] = "caption.partial"
    segment_id: str
    text: str
    lang: str
    t0: int
    t1: int
    speaker_label: str | None = None


class CaptionFinal(BaseModel):
    type: Literal["caption.final"] = "caption.final"
    segment_id: str
    plan: RenderPlan
    t0: int
    t1: int
    percept: PerceptEvent | None = None   # lattice details for "tap caption"


class RenderPlanMsg(BaseModel):
    """Sign output (pipelines C and D): gloss plan, round-trip read-back, avatar frames."""

    type: Literal["render.plan"] = "render.plan"
    plan: RenderPlan
    origin: Literal["speech", "compose", "repair"] = "compose"
    segment_id: str | None = None     # speech segment the plan was made from
    source_frame_id: str | None = None   # caption frame (speech) the plan was made from
    frame: SemanticFrame | None = None
    readback: list[LatticeSlot] = []
    frames: dict | None = None        # avatar2d.frames_json payload


class RepairRequest(BaseModel):
    type: Literal["repair.request"] = "repair.request"
    segment_id: str
    plan: RenderPlan
    percept: PerceptEvent | None = None


class HoldMsg(BaseModel):
    type: Literal["hold"] = "hold"
    reason: str
    segment_id: str | None = None
    frame_id: str | None = None


class SummaryUpdate(BaseModel):
    type: Literal["summary.update"] = "summary.update"
    data: dict


class SpeakerUpdate(BaseModel):
    type: Literal["speaker.update"] = "speaker.update"
    speakers: list[dict]              # [{id, label, conf, active}]


class TrustTick(BaseModel):
    type: Literal["trust.tick"] = "trust.tick"
    value: float
    gate: Gate


class ModeState(BaseModel):
    type: Literal["mode.state"] = "mode.state"
    mode: Mode
    vram_mb: int | None
    cloud: bool
    vram_free_mb: int | None = None
    warming: bool = False
    warning: str | None = None


class LatencyMsg(BaseModel):
    type: Literal["latency"] = "latency"
    stage: str
    ms: float


class TTSAudio(BaseModel):
    type: Literal["tts.audio"] = "tts.audio"
    pcm_b64: str
    frame_id: str


class TeachSuggest(BaseModel):
    type: Literal["teach.suggest"] = "teach.suggest"
    data: dict


class ErrorMsg(BaseModel):
    type: Literal["error"] = "error"
    code: str
    message: str


ServerMessage = Annotated[
    Union[
        SessionReady, CaptionPartial, CaptionFinal, RenderPlanMsg, RepairRequest, HoldMsg,
        SummaryUpdate, SpeakerUpdate, TrustTick, ModeState, LatencyMsg, TTSAudio, TeachSuggest, ErrorMsg,
    ],
    Field(discriminator="type"),
]
server_message = TypeAdapter(ServerMessage)
