"""Resolver router — rules fast path (Section 6).

The LLM path (Qwen3 via llama.cpp) arrives in Phase 3. Until then every
speech frame is built by templates straight from the lattice top-1, so
nothing is invented that the perceiver did not hear.
"""

from __future__ import annotations

import re

from .. import config
from ..fuse.trust import TrustResult
from ..schemas import Entity, Grounding, PerceptEvent, SemanticFrame, Unresolved

_WH = re.compile(r"^(who|what|when|where|why|how|which|whose|is|are|do|does|did|can|could|will|would|should)\b", re.I)
_REQUEST = re.compile(r"^(please|can you|could you|would you)\b", re.I)
_BACKCHANNEL = {"yeah", "yes", "ok", "okay", "mm", "mhm", "uh-huh", "right", "sure", "no"}


def _speech_act(text: str) -> str:
    t = text.strip()
    bare = re.sub(r"[^\w\s-]", "", t).lower()
    if bare in _BACKCHANNEL:
        return "backchannel"
    if _REQUEST.match(t):
        return "request"
    if t.endswith("?") or _WH.match(t):
        return "question"
    return "statement"


def join_slots(event: PerceptEvent) -> tuple[str, list[tuple[int, int] | None]]:
    """Top-1 words joined with spaces; returns text and per-slot char spans."""
    parts: list[str] = []
    spans: list[tuple[int, int] | None] = []
    pos = 0
    for slot in event.lattice:
        word = slot.cands[0].value if slot.cands else ""
        if not word:
            spans.append(None)
            continue
        if parts:
            pos += 1
        spans.append((pos, pos + len(word)))
        parts.append(word)
        pos += len(word)
    return " ".join(parts), spans


def needs_llm(event: PerceptEvent, trust: TrustResult) -> bool:
    """Phase 3 hook: rules are enough when every slot is confident."""
    return any(m < config.SLOT_UNCERTAIN_MARGIN for m in trust.slot_margins)


def needs_llm_gloss(frame: SemanticFrame) -> bool:
    """Sign fast path: short plain statements are fully handled by the ISL rules.

    Ambiguity is never sent to the LLM (it goes to the human as a repair).
    """
    if frame.unresolved or not frame.gloss:
        return False
    return (frame.question_type is not None or len(frame.gloss) >= config.SIGN_LLM_MIN_GLOSSES
            or frame.speech_act in ("request", "correction"))


def frame_from_percept(event: PerceptEvent, trust: TrustResult, speaker_id: str | None = None) -> SemanticFrame:
    text, spans = join_slots(event)
    grounding: list[Grounding] = []
    unresolved: list[Unresolved] = []
    entities: list[Entity] = []
    margins = iter(trust.slot_margins)
    for slot, span in zip(event.lattice, spans):
        if not slot.cands:
            continue
        margin = next(margins, 1.0)
        if span is None:
            continue
        t0 = slot.t0 if slot.t0 is not None else event.t0
        t1 = slot.t1 if slot.t1 is not None else event.t1
        grounding.append(Grounding(span=span, percept_ids=[event.id], t=(t0, t1)))
        if margin < config.SLOT_UNCERTAIN_MARGIN:
            alts = [c.value for c in slot.cands]
            unresolved.append(Unresolved(slot=slot.slot, cands=alts, reason="low_margin"))
            entities.append(Entity(text=slot.cands[0].value, type="word", resolved_from="lattice",
                                   alternatives=alts[1:], margin=round(margin, 3)))
    if not grounding:
        grounding.append(Grounding(span=(0, len(text)), percept_ids=[event.id], t=(event.t0, event.t1)))
    return SemanticFrame(
        utterance=text,
        lang=event.lang_hint,
        speech_act=_speech_act(text),
        entities=entities,
        grounding=grounding,
        unresolved=unresolved,
        trust=round(trust.value, 4),
        speaker_id=speaker_id,
        provenance={"resolver": "rules", "escalated_to_cloud": False, "path": "rules", "source": event.source},
    )
