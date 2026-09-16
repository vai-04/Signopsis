"""SemanticFrame (with ISL gloss) -> SignTarget: timing, fingerspelling, non-manual track."""

from __future__ import annotations

from .. import config
from ..resolve import isl_vocab as V
from ..resolve.isl_rules import nonmanual_for
from ..schemas import GlossToken, NMKey, SemanticFrame, SignTarget
from .avatar2d import build_timeline
from .fingerspell import fs_duration, fs_letters
from .signs import LEXICON, has_sign


def plan_sign(frame: SemanticFrame, sign_lang: str = "isl") -> SignTarget:
    span_of = {g.gloss_index: g.span for g in frame.grounding if g.gloss_index is not None}
    unresolved_slots = {u.slot for u in frame.unresolved}
    items: list[GlossToken] = []
    for gi, g in enumerate(frame.gloss):
        span = span_of.get(gi)
        if g.startswith("FS:"):
            letters = fs_letters(g[3:])
            items.append(GlossToken(g=g, dur_ms=fs_duration(letters), fs_fallback=letters,
                                    fingerspelled=True, conf=1.0, source_span=span))
        elif not has_sign(g):
            # in the vocabulary but no motion in the lexicon yet -> spell it
            letters = fs_letters(g.replace("-", ""))
            items.append(GlossToken(g=g, dur_ms=fs_duration(letters), fs_fallback=letters,
                                    fingerspelled=True, conf=1.0, source_span=span))
        else:
            dur = LEXICON[g]["dur"]
            if frame.prosody.pace == "fast":
                dur = int(dur * config.SIGN_FAST_PACE)
            items.append(GlossToken(g=g, dur_ms=dur, fs_fallback=fs_letters(g.replace("-", "")),
                                    conf=0.5 if gi in unresolved_slots else 1.0, source_span=span))
    # Affect below 0.5 confidence is rendered neutral (Section 5).
    affect = frame.prosody.affect if frame.prosody.conf >= 0.5 else "neutral"
    return SignTarget(sign_lang=sign_lang, gloss=items, affect=affect)


def fix_fingerspelled_durations(target: SignTarget) -> None:
    """After the round-trip gate: degraded glosses now play as letters."""
    for it in target.gloss:
        if it.fingerspelled and it.fs_fallback:
            it.dur_ms = fs_duration(it.fs_fallback)


def nonmanual_track(frame: SemanticFrame, target: SignTarget) -> list[NMKey]:
    segs, total = build_timeline(target)
    nm = nonmanual_for(frame)
    keys = [NMKey(t=0, brow=nm.brow, head="neutral", mouth="neutral")]
    starts: dict[int, int] = {}
    ends: dict[int, int] = {}
    for s in segs:
        starts.setdefault(s.gloss_index, s.start)
        ends[s.gloss_index] = s.end
    # negation: headshake over NOT
    for gi, it in enumerate(target.gloss):
        if it.g in ("NOT", "NO") and gi in starts:
            keys += [NMKey(t=max(starts[gi] - 80, 0), head="shake"), NMKey(t=ends[gi] + 80, head="neutral")]
    if frame.question_type and target.gloss:
        last = len(target.gloss) - 1
        keys.append(NMKey(t=starts.get(last, 0), head="tilt_fwd"))
        keys.append(NMKey(t=total - 150, brow="neutral", head="neutral"))
    elif frame.speech_act == "statement" and not frame.negated and target.gloss:
        last = len(target.gloss) - 1
        keys.append(NMKey(t=ends.get(last, 0), head="nod"))
        keys.append(NMKey(t=total - 100, head="neutral"))
    if target.affect == "urgent":
        keys.append(NMKey(t=0, mouth="open"))
    keys.sort(key=lambda k: k.t)
    return keys


def back_translate(target: SignTarget, readback: list[str], frame: SemanticFrame) -> str:
    """What the recognizer read back from the avatar, in words (S11 preview)."""
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
