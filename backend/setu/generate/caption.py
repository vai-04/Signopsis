"""SemanticFrame + gate -> RenderPlan with a caption target (Section 11.2)."""

from __future__ import annotations

from ..repair.hold_reasons import reason_for
from ..resolve.router import join_slots
from ..schemas import CaptionTarget, Gate, PerceptEvent, RenderPlan, Repair, RepairOption, SemanticFrame

BADGE = {"emit": "high", "repair": "medium", "hold": "low"}


def plan_caption(frame: SemanticFrame, event: PerceptEvent, gate: Gate, speaker_label: str | None = None) -> RenderPlan:
    if gate == "hold":
        # Never show a guess: the UI renders a dashed hold card with the reason.
        return RenderPlan(frame_id=frame.id, gate="hold", targets=[],
                          repair=Repair(type="hold", reason=reason_for(event)))

    _, spans = join_slots(event)
    span_by_slot = {s.slot: sp for s, sp in zip(event.lattice, spans)}
    uncertain = [span_by_slot[u.slot] for u in frame.unresolved if span_by_slot.get(u.slot)]

    caption = CaptionTarget(
        lang=frame.lang, text=frame.utterance, trust_badge=BADGE[gate],
        speaker_label=speaker_label, uncertain_spans=uncertain,
    )
    repair = None
    if gate == "repair":
        repair = _repair_for(frame, event)
    return RenderPlan(frame_id=frame.id, gate=gate, targets=[caption], repair=repair)


def _repair_for(frame: SemanticFrame, event: PerceptEvent) -> Repair:
    if not frame.unresolved:
        return Repair(type="disambiguate", reason="I'm not fully sure I heard this right", options=[])
    first = frame.unresolved[0]
    slot = next(s for s in event.lattice if s.slot == first.slot)
    options = [RepairOption(gloss_or_word=c.value, score=round(c.score, 3)) for c in slot.cands if c.value][:2]
    word = slot.cands[0].value if slot.cands else ""
    if len(options) > 1:
        reason = f"Did they say “{options[0].gloss_or_word}” or “{options[1].gloss_or_word}”?"
    else:
        reason = f"I'm not sure about “{word}”"
    return Repair(type="homophone" if len(options) > 1 else "disambiguate", reason=reason, options=options)
