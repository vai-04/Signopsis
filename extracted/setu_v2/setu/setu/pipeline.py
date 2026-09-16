"""Pipeline D: text -> sign.

    text -> [L3 resolver] SemanticFrame -> plan SignTarget -> [round-trip gate]
         -> [L2-style gate] RenderPlan -> (2D avatar frames for the viewer)

Everything downstream of this module consumes RenderPlan only.
"""
from __future__ import annotations

import os
import time
from typing import Optional

from setu.generate import roundtrip as RT
from setu.generate.avatar2d import build_timeline, frames_json
from setu.generate.signs import FS_DUR, LEXICON, fs_letters, has_sign
from setu.resolve import vocab as V
from setu.resolve.rules import nonmanual_for, text_to_frame
from setu.schemas import (CaptionTarget, GlossItem, NMKey, RenderPlan, Repair,
                          RepairOption, SemanticFrame, SignTarget)

EMIT_AT = 0.75
HOLD_BELOW = 0.40
EMIT_AT_HIGH_STAKES = 0.85
ADVISORY = ("Medical / legal context detected. SETU is a supplement, not a replacement: "
            "please use a certified ISL interpreter for consent, diagnosis or legal matters.")


def _resolve(text: str, resolutions: dict[int, str]) -> SemanticFrame:
    """L3 dispatch. SETU_RESOLVER=ollama tries the local LLM, falls back to rules."""
    if os.getenv("SETU_RESOLVER", "rules") == "ollama":
        from setu.resolve.llm import llm_frame
        frame = llm_frame(text, resolutions)
        if frame is not None:
            return frame
    frame, _ = text_to_frame(text, resolutions)
    return frame


def plan_sign(frame: SemanticFrame, text: str) -> SignTarget:
    span_of = {g.gloss_index: g.span for g in frame.grounding}
    items = []
    for gi, g in enumerate(frame.gloss):
        span = span_of.get(gi)
        if g.startswith("FS:"):
            word = g[3:]
            items.append(GlossItem(g=g, dur_ms=0, fs_fallback=fs_letters(word),
                                   fingerspelled=True, conf=1.0, source_span=span))
        elif not has_sign(g):
            # in the vocabulary but no motion in the lexicon yet -> spell it
            items.append(GlossItem(g=g, dur_ms=0, fs_fallback=fs_letters(g.replace("-", "")),
                                   fingerspelled=True, conf=1.0, source_span=span))
        else:
            unresolved = any(u.slot == gi for u in frame.unresolved)
            items.append(GlossItem(g=g, dur_ms=LEXICON[g]["dur"],
                                   fs_fallback=fs_letters(g.replace("-", "")),
                                   conf=0.5 if unresolved else 1.0, source_span=span))
    target = SignTarget(gloss=items, affect=frame.prosody.affect)
    if frame.prosody.pace == "fast":
        for it in target.gloss:
            it.dur_ms = int(it.dur_ms * 0.85)
    return target


def nonmanual_track(frame: SemanticFrame, target: SignTarget) -> list[NMKey]:
    segs, total = build_timeline(target)
    nm = nonmanual_for(frame)
    keys = [NMKey(t=0, brow=nm.brow, head="neutral", mouth="neutral")]
    starts = {}
    ends = {}
    for s in segs:
        starts.setdefault(s.gloss_index, s.start)
        ends[s.gloss_index] = s.end
    # negation: headshake over NOT
    for gi, it in enumerate(target.gloss):
        if it.g in ("NOT", "NO") and gi in starts:
            keys += [NMKey(t=starts[gi] - 80, head="shake"), NMKey(t=ends[gi] + 80, head="neutral")]
    if frame.question_type and target.gloss:
        last = len(target.gloss) - 1
        keys.append(NMKey(t=starts.get(last, 0), head="tilt_fwd"))
        keys.append(NMKey(t=total - 150, brow="neutral", head="neutral"))
    elif frame.speech_act == "statement" and not frame.negated and target.gloss:
        last = len(target.gloss) - 1
        keys.append(NMKey(t=ends.get(last, 0), head="nod"))
        keys.append(NMKey(t=total - 100, head="neutral"))
    if frame.prosody.affect == "urgent":
        keys.append(NMKey(t=0, mouth="open"))
    keys.sort(key=lambda k: k.t)
    return keys


def back_translate(target: SignTarget, readback: list[str], frame: SemanticFrame) -> str:
    words = []
    for it, rb in zip(target.gloss, readback):
        if it.fingerspelled:
            words.append(f'"{rb.lower()}"')
        else:
            words.append(V.BACK_GLOSS.get(rb, rb.lower().replace("-", " ")))
    s = " · ".join(words)
    if frame.question_type == "wh":
        s += "  (wh-question)"
    elif frame.question_type == "yesno":
        s += "  (yes/no question)"
    if frame.negated:
        s += "  (negated)"
    return s


def text_to_sign(text: str, resolutions: Optional[dict[int, str]] = None,
                 with_frames: bool = False, seed: int = 7) -> dict:
    """Run pipeline D. Returns {"frame", "plan", "readback", ["frames"]} (all JSON-able)."""
    resolutions = resolutions or {}
    tm = {}
    t0 = time.perf_counter()
    frame = _resolve(text, resolutions)
    tm["resolve"] = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    target = plan_sign(frame, text)
    threshold = RT.THRESHOLD_HIGH_STAKES if frame.high_stakes else RT.THRESHOLD
    gate_res = RT.roundtrip_gate(target, threshold=threshold, seed=seed)
    for it in target.gloss:
        if it.fingerspelled and it.fs_fallback:
            n = len(it.fs_fallback.split("-"))
            it.dur_ms = n * FS_DUR + (n - 1) * 60
    target.nonmanual = nonmanual_track(frame, target)
    target.total_ms = build_timeline(target)[1]
    target.back_translation = back_translate(target, gate_res.readback, frame)
    tm["plan+roundtrip"] = (time.perf_counter() - t1) * 1000

    # ---- gate
    trust = round(frame.trust * target.roundtrip_score, 3)
    frame.trust = trust
    emit_at = EMIT_AT_HIGH_STAKES if frame.high_stakes else EMIT_AT
    repair = None
    if not target.gloss:
        gate, reason = "hold", "Nothing signable in this text."
    elif frame.unresolved:
        u = frame.unresolved[0]
        gate, reason = "repair", f'"{u.source_text}" is ambiguous ({" / ".join(u.cands)}); the author must choose.'
        repair = Repair(type="disambiguate", slot=u.slot, token_index=u.token_index,
                        prompt=f'Which did you mean by "{u.source_text}"?',
                        options=[RepairOption(gloss=c, label=V.BACK_GLOSS.get(c, c.lower()),
                                              clip=f"ref/isl/{c.lower()}.mp4") for c in u.cands])
    elif trust < HOLD_BELOW:
        gate, reason = "hold", f"Round-trip trust {trust:.2f} < {HOLD_BELOW}: the avatar can't sign this clearly."
    elif trust < emit_at:
        gate, reason = "repair", f"Trust {trust:.2f} < {emit_at}: confirm the preview before sending."
        repair = Repair(type="confirm", slot=-1, prompt="The signing may be unclear. Send anyway?",
                        options=[RepairOption(gloss="SEND", label="Send as shown"),
                                 RepairOption(gloss="REPHRASE", label="Let me rephrase")])
    else:
        gate, reason = "emit", f"Trust {trust:.2f} ≥ {emit_at}."
    if gate_res.degraded:
        names = ", ".join(target.gloss[i].g for i in gate_res.degraded)
        reason += f" Fingerspelled after failed read-back: {names}."

    badge = "high" if trust >= emit_at else "medium" if trust >= HOLD_BELOW else "low"
    caption = CaptionTarget(lang=frame.lang, text=text, trust_badge=badge,
                            forced=bool(gate_res.degraded))
    tm["total"] = (time.perf_counter() - t0) * 1000
    plan = RenderPlan(frame_id=frame.id, gate=gate, gate_reason=reason,
                      targets=[caption, target], repair=repair,
                      advisory=ADVISORY if frame.high_stakes else None,
                      timings_ms={k: round(v, 1) for k, v in tm.items()})
    out = {
        "frame": frame.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
        "readback": [s.model_dump(mode="json") for s in gate_res.lattices],
    }
    if with_frames:
        out["frames"] = frames_json(target)
    return out
