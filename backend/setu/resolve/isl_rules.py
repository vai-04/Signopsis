"""Rule-based text -> ISL gloss resolver (L3, offline, deterministic).

Pipeline:
  normalize -> tokenize (with char spans) -> per-token language ID
  -> phrase match -> lexical lookup (EN/HI) -> ambiguity handling
  -> drop function words -> ISL reorder -> non-manual track -> SemanticFrame

The grammar rules are documented for consultants in grammar/isl.md.
Every rule here must have a line there.

Input comes from typed text (Compose, pipeline D) or from an emitted speech
caption (pipeline C). In the speech case the grounding points at the speech
PerceptEvent, so every gloss traces back to audio the ASR actually heard.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .. import config
from ..schemas import (Candidate, Entity, Grounding, LatticeSlot, NonManual, PerceptEvent, Prosody,
                       SemanticFrame, Unresolved)
from . import isl_vocab as V

RESOLVER_NAME = "rules-isl-v1"

CONTRACTIONS = {
    "don't": "do not", "doesn't": "does not", "didn't": "did not", "can't": "can not",
    "cannot": "can not", "won't": "will not", "isn't": "is not", "aren't": "are not",
    "wasn't": "was not", "weren't": "were not", "i'm": "i am", "you're": "you are",
    "he's": "he is", "she's": "she is", "it's": "it is", "we're": "we are",
    "they're": "they are", "what's": "what is", "where's": "where is", "who's": "who is",
    "how's": "how is", "i'll": "i will", "you'll": "you will", "i've": "i have",
    "i'd": "i would", "let's": "let us", "haven't": "have not", "hasn't": "has not",
}
YESNO_STARTERS = {"do", "does", "did", "is", "are", "am", "was", "were", "can", "could",
                  "will", "would", "should", "have", "has", "kya"}
DEVANAGARI = re.compile(r"[ऀ-ॿ]")
TOKEN_RE = re.compile(r"[ऀ-ॿ]+|[A-Za-z]+(?:'[A-Za-z]+)?|\d+|[?!.,]")


@dataclass
class Tok:
    text: str
    span: tuple[int, int]
    lang: str = "en"
    gloss: Optional[str] = None
    cands: list[str] = field(default_factory=list)
    kind: str = "word"          # word | punct | stop | unknown | proper
    capital: bool = False
    seg: int = 0                # sentence segment (reordering never crosses it)


def _tokenize(text: str) -> list[Tok]:
    toks = []
    for m in TOKEN_RE.finditer(text):
        raw = m.group(0)
        toks.append(Tok(text=raw, span=(m.start(), m.end()), capital=raw[:1].isupper()))
    return toks


def _expand_contractions(toks: list[Tok]) -> list[Tok]:
    out = []
    for t in toks:
        exp = CONTRACTIONS.get(t.text.lower())
        if exp:
            for w in exp.split():
                out.append(Tok(text=w, span=t.span, capital=False))
        elif t.text.lower().endswith("n't"):
            out.append(Tok(text=t.text[:-3], span=t.span))
            out.append(Tok(text="not", span=t.span))
        elif t.text.lower().endswith("'s"):
            out.append(Tok(text=t.text[:-2], span=t.span, capital=t.capital))
        else:
            out.append(t)
    return out


def detect_lang(toks: list[Tok]) -> str:
    """Per-token language ID, returns sentence tag: en | hi | hi-en."""
    hi = en = 0
    for t in toks:
        if t.kind == "punct" or not t.text[0].isalpha() and not DEVANAGARI.match(t.text):
            continue
        w = t.text.lower()
        if DEVANAGARI.search(w):
            t.lang = "hi"
        elif (w in V.HI or w in V.HI_AMBIGUOUS or w in V.STOP_HI) and w not in V.EN and w not in V.STOP_EN:
            t.lang = "hi"
        else:
            t.lang = "en"
        hi += t.lang == "hi"
        en += t.lang == "en"
    # shared words (bank, doctor, school, to, me) inherit the majority
    if hi and en:
        tag = "hi-en" if min(hi, en) / (hi + en) >= 0.2 else ("hi" if hi > en else "en")
    else:
        tag = "hi" if hi else "en"
    if tag in ("hi", "hi-en"):
        for t in toks:
            w = t.text.lower()
            if t.lang == "en" and w in V.STOP_HI and w not in V.EN:
                t.lang = "hi"
            if t.lang == "en" and w in ("me",) and hi > en:
                t.lang = "hi"   # Hinglish "ghar me" = "in the house"
    return tag


def _lookup(toks: list[Tok], lang: str) -> None:
    i = 0
    low = [t.text.lower() for t in toks]
    while i < len(toks):
        t = toks[i]
        if t.text in "?!.,":
            t.kind = "punct"; i += 1; continue
        # phrases (English, up to 3 words)
        matched = False
        for n in (3, 2):
            key = " ".join(low[i:i + n])
            if len(low[i:i + n]) == n and key in V.PHRASES_EN:
                gl = V.PHRASES_EN[key]
                t.gloss = gl[0]
                t.span = (t.span[0], toks[i + n - 1].span[1])
                extra = [Tok(text=g, span=t.span, gloss=g) for g in gl[1:]]
                if len(gl) > 1:        # rule 8: multi-sign greetings stay together, up front
                    t.kind = "phrase"
                    for e in extra:
                        e.kind = "phrase"
                for k in range(1, n):
                    toks[i + k].kind = "stop"
                toks[i + 1:i + 1] = extra
                low[i + 1:i + 1] = [e.text.lower() for e in extra]
                i += 1 + len(extra) + (n - 1)
                matched = True
                break
        if matched:
            continue
        w = low[i]
        if t.lang == "hi":
            if w in V.HI_AMBIGUOUS:
                t.cands = list(V.HI_AMBIGUOUS[w])
            elif w in V.HI:
                t.gloss = V.HI[w]
            elif w in V.STOP_HI:
                t.kind = "stop"
            elif w in V.EN:
                t.gloss = V.EN[w]
            else:
                t.kind = "unknown"
        else:
            if w in V.EN:
                t.gloss = V.EN[w]
            elif w in V.STOP_EN:
                t.kind = "stop"
            elif w in V.HI and lang != "en":
                t.gloss = V.HI[w]
            elif w.isdigit():
                t.kind = "unknown"
            else:
                t.kind = "unknown"
        if t.kind == "unknown" and t.capital and i > 0:
            t.kind = "proper"
        i += 1


def _resolve_ambiguity(toks: list[Tok], context_words: set[str], resolutions: dict[int, str]):
    """Collapse lexical ambiguity with context; otherwise leave it for repair."""
    past = bool(context_words & (V.HI_PAST | V.PAST_FORMS))
    future = bool(context_words & (V.HI_FUTURE | V.FUTURE_MARKERS))
    for idx, t in enumerate(toks):
        if not t.cands:
            continue
        if idx in resolutions:
            t.gloss = resolutions[idx]; t.kind = "user"; continue
        if set(t.cands) == {"YESTERDAY", "TOMORROW"}:
            if past and not future:
                t.gloss = "YESTERDAY"; t.kind = "context"
            elif future and not past:
                t.gloss = "TOMORROW"; t.kind = "context"


def text_to_frame(text: str, resolutions: Optional[dict[int, str]] = None, *,
                  source: Optional[PerceptEvent] = None, t_ms: tuple[int, int] = (0, 0),
                  speaker_id: Optional[str] = None) -> tuple[SemanticFrame, PerceptEvent]:
    """Resolve raw text into a SemanticFrame carrying the ISL gloss.

    `resolutions` maps *token index* -> chosen gloss (from a repair tap).
    `source` is the speech PerceptEvent the text came from (pipeline C);
    without it a synthetic "text" PerceptEvent is created (pipeline D).
    Returns the frame plus the PerceptEvent it is grounded on.
    """
    resolutions = resolutions or {}
    text = (text or "").strip()
    toks = _expand_contractions(_tokenize(text))
    lang = detect_lang(toks)
    _lookup(toks, lang)
    seg = 0
    for t in toks:
        t.seg = seg
        if t.text in "?!.," and t.kind == "punct":
            seg += 1
    words = {t.text.lower() for t in toks}
    _resolve_ambiguity(toks, words, resolutions)

    t0, t1 = (source.t0, source.t1) if source is not None else t_ms
    percept = source or PerceptEvent(
        t0=t0, t1=t1, channel="text", source="keyboard", lang_hint=lang,
        lattice=[LatticeSlot(slot=i, cands=[Candidate(value=tk.text, score=1.0)]) for i, tk in enumerate(toks)],
    )

    content = [t for t in toks if t.kind not in ("punct", "stop")]
    low = [t.text.lower() for t in toks if t.kind != "punct"]
    is_question = text.endswith("?") or (bool(low) and low[0] in YESNO_STARTERS and low[0] != "kya") \
        or any(t.gloss and V.CATEGORY.get(t.gloss) == "WH" for t in content) \
        or (bool(low) and low[0] == "kya" and text.endswith("?"))
    has_wh = any(t.gloss and V.CATEGORY.get(t.gloss) == "WH" for t in content)
    # Hindi "kya" at sentence start without other WH = yes/no particle, not WHAT
    if low and low[0] == "kya" and lang != "en":
        first = next((t for t in content if t.text.lower() == "kya"), None)
        others_wh = [t for t in content if t is not first and t.gloss and V.CATEGORY.get(t.gloss) == "WH"]
        if first is not None and (not others_wh) and len(content) > 1:
            first.kind = "stop"; first.gloss = None
            content = [t for t in content if t is not first]
            has_wh = False
            is_question = True
    qtype = ("wh" if has_wh else "yesno") if is_question else None
    negated = any(t.gloss in ("NOT",) for t in content)

    # ---- build (gloss, category, tok, tok_index) list
    items = []
    unresolved_pending = []
    for t in content:
        ti = toks.index(t)
        if t.gloss:
            cat = "PHRASE" if t.kind == "phrase" else V.CATEGORY.get(t.gloss, "NOUN")
            items.append([t.gloss, cat, t, ti])
        elif t.cands:
            # unresolved: keep top candidate as placeholder, flag it
            items.append([t.cands[0], V.CATEGORY.get(t.cands[0], "NOUN"), t, ti])
            unresolved_pending.append((len(items) - 1, t, ti))
        elif t.kind in ("unknown", "proper"):
            items.append(["FS:" + t.text.upper(), "NOUN", t, ti])

    # ---- ISL completive: past tense with no explicit time word -> FINISH after verb
    has_time = any(c == "TIME" for _, c, _, _ in items)
    is_past = bool(words & (V.PAST_FORMS | V.HI_PAST)) and not is_question
    add_finish = is_past and not has_time and any(c == "VERB" for _, c, _, _ in items)

    # ---- reorder: PHRASE | TIME | topic(PRON/NOUN/ADJ/FS) | VERB | ASPECT | NEG | WH
    order = {"PHRASE": 0, "AFFIRM": 0, "TIME": 1, "PRON": 2, "NOUN": 2, "ADJ": 3,
             "VERB": 4, "ASPECT": 5, "NEG": 6, "WH": 7}
    items.sort(key=lambda it: (it[2].seg, order.get(it[1], 2)))   # stable within a sentence
    # "NO" as an answer word stays up front
    if add_finish:
        pos = max(i for i, it in enumerate(items) if it[1] == "VERB") + 1
        items.insert(pos, ["FINISH", "ASPECT", items[pos - 1][2], -1])

    # de-duplicate immediate repeats (e.g. "my name" + "name")
    dedup = []
    for it in items:
        if dedup and dedup[-1][0] == it[0]:
            continue
        dedup.append(it)
    items = dedup

    gloss = [it[0] for it in items]
    grounding, entities, unresolved = [], [], []
    for gi, (g, cat, t, ti) in enumerate(items):
        if t is None:
            continue
        grounding.append(Grounding(span=t.span, percept_ids=[percept.id], t=(t0, t1), gloss_index=gi))
        if g.startswith("FS:"):
            entities.append(Entity(text=t.text, type="proper" if t.kind == "proper" else "unknown",
                                   resolved_from="fingerspell", margin=0.0))
        elif t.cands:
            entities.append(Entity(text=t.text, type="time" if cat == "TIME" else "thing",
                                   resolved_from={"context": "context", "user": "user"}.get(t.kind, "lattice"),
                                   alternatives=[c for c in t.cands if c != g],
                                   margin=1.0 if t.gloss else 0.0))
    for gi, it in enumerate(items):
        t = it[2]
        if t is not None and t.cands and not t.gloss:
            unresolved.append(Unresolved(slot=gi, cands=t.cands, reason="lexical_ambiguity",
                                         source_text=t.text, token_index=it[3]))

    # ---- prosody
    affect, intensity = "neutral", 0.3
    if text.endswith("!"):
        intensity = 0.8
        affect = "urgent" if any(g in ("HELP", "PAIN", "HOSPITAL", "NOW") for g in gloss) else "joy"
    if any(g in ("SAD", "SORRY") for g in gloss):
        affect = "sad"
    affect_conf = 0.6 if affect != "neutral" else 0.0   # punctuation/lexicon cue only
    emphasis = [it[2].text for it in items if it[2] is not None and it[2].text.isupper() and len(it[2].text) > 1]

    speech_act = "question" if is_question else (
        "backchannel" if gloss and all(V.CATEGORY.get(g) in ("PHRASE", "AFFIRM", "NEG") for g in gloss) and len(gloss) <= 2
        else "request" if (words & {"please", "kripya"}) or (gloss and gloss[0] == "HELP") else "statement")

    high = any(g in V.HIGH_STAKES for g in gloss) or bool(words & V.HIGH_STAKES_WORDS)

    # resolver confidence: unresolved slots dominate
    trust = 1.0
    if unresolved:
        trust = config.SIGN_AMBIGUOUS_TRUST
    n_fs = sum(g.startswith("FS:") for g in gloss)
    if gloss:
        trust *= 1.0 - config.SIGN_FS_PENALTY * (n_fs / len(gloss))
    if not grounding:                     # nothing signable: ground the frame on the whole input
        grounding.append(Grounding(span=(0, len(text)), percept_ids=[percept.id], t=(t0, t1)))

    frame = SemanticFrame(
        utterance=text, lang=lang, speech_act=speech_act, question_type=qtype,
        negated=negated, entities=entities,
        prosody=Prosody(affect=affect, intensity=intensity, emphasis=emphasis,
                        pace="fast" if affect == "urgent" else "normal", conf=affect_conf),
        grounding=grounding, unresolved=unresolved, gloss=gloss,
        high_stakes=high, trust=round(trust, 3), speaker_id=speaker_id,
        provenance={"resolver": RESOLVER_NAME, "escalated_to_cloud": False, "path": "rules",
                    "source": percept.source},
    )
    return frame, percept


def nonmanual_for(frame: SemanticFrame) -> NonManual:
    if frame.question_type == "wh":
        return NonManual(brow="furrowed", head="tilt_fwd")
    if frame.question_type == "yesno":
        return NonManual(brow="raised", head="tilt_fwd")
    if frame.negated:
        return NonManual(head="shake")
    return NonManual()
