"""SemanticFrame — resolver output (Section 4.2)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .percept import new_id


class Entity(BaseModel):
    text: str
    type: str
    resolved_from: Literal["lattice", "memory", "context", "user", "lexicon", "fingerspell"]
    alternatives: list[str] = []
    margin: float | None = None


class Prosody(BaseModel):
    affect: Literal["neutral", "joy", "sad", "angry", "surprised", "urgent"] = "neutral"
    intensity: float = 0.0
    emphasis: list[str] = []
    pace: Literal["slow", "normal", "fast"] = "normal"
    conf: float = 0.0


class Grounding(BaseModel):
    span: tuple[int, int]             # char offsets in utterance
    percept_ids: list[str]
    t: tuple[int, int]
    gloss_index: int | None = None    # sign path: which output gloss this span produced


class Unresolved(BaseModel):
    slot: int
    cands: list[str]
    reason: Literal["low_margin", "unknown_sign", "low_quality", "homophone",
                    "lexical_ambiguity", "unknown_word", "roundtrip_fail"]
    source_text: str = ""
    token_index: int | None = None    # sign path: key for a repair resolution


class SemanticFrame(BaseModel):
    utterance: str                    # MUST be the first field emitted by the LLM (streaming)
    id: str = Field(default_factory=lambda: new_id("sf"))
    lang: str
    speech_act: Literal["statement", "question", "request", "correction", "backchannel"]
    entities: list[Entity] = []
    prosody: Prosody = Field(default_factory=Prosody)
    grounding: list[Grounding]        # required, non-empty
    unresolved: list[Unresolved] = []
    trust: float
    speaker_id: str | None = None
    provenance: dict                  # {"resolver": ..., "escalated_to_cloud": bool, "path": "rules"|"llm"}
    # Sign-generation extensions (pipelines C/D); empty for caption-only frames.
    gloss: list[str] = []
    question_type: Literal["wh", "yesno"] | None = None
    negated: bool = False
    high_stakes: bool = False

    @field_validator("grounding")
    @classmethod
    def _grounding_non_empty(cls, v: list[Grounding]) -> list[Grounding]:
        if not v:
            raise ValueError("grounding must be non-empty")
        return v
