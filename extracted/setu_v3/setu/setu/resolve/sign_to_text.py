"""L3 for sign -> text: collapse the sign lattice with context, then realise
the ISL gloss as an English (or Hindi) sentence with grounding.

1. Context decoding (Viterbi over slots): visual log-prob + ISL category
   order model + co-occurrence + conversation memory + this user's jargon.
2. Per-slot posterior with the rest of the path fixed -> context margin.
   Anything still ambiguous is reported in `unresolved`; it is never hidden.
3. Realisation: ISL (time-topic-comment, verb-final, wh-last) -> English
   SVO with tense from time words / FINISH, questions from the face,
   negation from NOT or a head shake. Every output word carries the slot
   ids it came from; function words inherit their constituent's slots.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional

from setu.resolve.vocab import CATEGORY, HIGH_STAKES

# ------------------------------------------------------------------ context model
CAT = dict(CATEGORY)
TRANS = {   # P(next category | category), ISL order: PHRASE TIME PRON/NOUN ADJ VERB ASPECT NEG WH
    "^":      {"PHRASE": .18, "AFFIRM": .05, "TIME": .20, "PRON": .30, "NOUN": .18, "ADJ": .03, "VERB": .03, "WH": .02, "NEG": .01},
    "PHRASE": {"PHRASE": .15, "TIME": .12, "PRON": .25, "NOUN": .12, "ADJ": .05, "VERB": .05, "WH": .05, "$": .21},
    "AFFIRM": {"PHRASE": .1, "PRON": .25, "NOUN": .1, "VERB": .1, "$": .45},
    "TIME":   {"TIME": .05, "PRON": .45, "NOUN": .25, "VERB": .1, "ADJ": .04, "WH": .06, "$": .05},
    "PRON":   {"PRON": .06, "NOUN": .38, "ADJ": .12, "VERB": .22, "WH": .06, "NEG": .03, "TIME": .03, "$": .10},
    "NOUN":   {"NOUN": .12, "ADJ": .10, "VERB": .35, "WH": .15, "NEG": .04, "PRON": .06, "$": .18},
    "ADJ":    {"NOUN": .15, "VERB": .1, "NEG": .1, "WH": .05, "$": .6},
    "VERB":   {"ASPECT": .18, "NEG": .18, "WH": .14, "NOUN": .08, "VERB": .06, "$": .36},
    "ASPECT": {"NEG": .1, "WH": .1, "$": .8},
    "NEG":    {"WH": .1, "$": .9},
    "WH":     {"$": .95, "NOUN": .05},
}
EPS = 0.01
COOC = {frozenset(p) for p in [
    ("WANT", "WATER"), ("DRINK", "WATER"), ("EAT", "FOOD"), ("WANT", "FOOD"), ("BANK", "MONEY"),
    ("GO", "BANK"), ("GO", "HOME"), ("GO", "SCHOOL"), ("GO", "HOSPITAL"), ("COME", "HOME"),
    ("DOCTOR", "HOSPITAL"), ("MEDICINE", "PAIN"), ("NEED", "MEDICINE"), ("NEED", "DOCTOR"),
    ("NAME", "WHAT"), ("YOUR", "NAME"), ("MY", "NAME"), ("TIME", "WHAT"), ("WHERE", "TOILET"),
    ("WHERE", "HOSPITAL"), ("WHERE", "HOME"), ("SICK", "DOCTOR"), ("HELP", "NEED"), ("WORK", "GO"),
    ("BOOK", "SCHOOL"), ("MOTHER", "SICK"), ("FRIEND", "COME"), ("HOW-MANY", "MONEY"), ("THANK-YOU", "HELP"),
    ("NEED", "HELP"), ("PAIN", "DOCTOR"), ("NOT", "UNDERSTAND"), ("KNOW", "NOT"), ("MORNING", "GOOD"),
    ("NIGHT", "GOOD"), ("HOW", "YOU"),
]}
LAMBDA, MU, HIST = 0.8, 1.6, 0.5
AMBIG_MARGIN = 0.35


def cat_of(g: str) -> str:
    if g.startswith("FS:") or g == "?":
        return "NOUN"
    return CAT.get(g, "NOUN")


@dataclass
class SlotIn:
    cands: list[tuple[str, float]]        # visual lattice (after L2), gloss or "FS:WORD"
    percept_id: str
    t: tuple[float, float]
    kind: str = "sign"                    # sign | fs | unknown
    negated: bool = False                 # head shake during this slot
    locked: Optional[str] = None          # set by a repair answer


@dataclass
class Resolved:
    gloss: list[str]
    post: list[list[tuple[str, float]]]   # context posterior per slot (top 3)
    margins: list[float]
    unresolved: list[int]
    sources: list[str]                    # lattice | context | user


def _trans(a: str, b: str) -> float:
    return math.log(TRANS.get(a, {}).get(b, EPS) + EPS)


def decode_context(slots: list[SlotIn], history: list[str] = (),
                   jargon: Optional[Callable[[list[str], Optional[str], Optional[str]], dict]] = None) -> Resolved:
    n = len(slots)
    if n == 0:
        return Resolved([], [], [], [], [])
    hist = set(history)
    options = []
    for s in slots:
        if s.locked:
            options.append([(s.locked, 0.0)])
            continue
        c = [(g, math.log(max(p, 1e-4))) for g, p in s.cands[:3]]
        options.append(c)

    def local(i, g, prev_g, next_g=None):
        sc = LAMBDA * _trans(cat_of(prev_g) if prev_g else "^", cat_of(g))
        if prev_g and frozenset((prev_g, g)) in COOC:
            sc += MU
        if g in hist or any(frozenset((h, g)) in COOC for h in hist):
            sc += HIST
        return sc

    # window co-occurrence (±2) handled after Viterbi as a rescoring pass
    best = [dict() for _ in range(n)]      # g -> (score, back)
    for g, lp in options[0]:
        best[0][g] = (lp + local(0, g, None), None)
    for i in range(1, n):
        for g, lp in options[i]:
            cand = []
            for pg, (ps, _) in best[i - 1].items():
                cand.append((ps + lp + local(i, g, pg), pg))
            best[i][g] = max(cand)
    end = max(best[-1].items(), key=lambda kv: kv[1][0] + LAMBDA * _trans(cat_of(kv[0]), "$"))
    path = [end[0]]
    for i in range(n - 1, 0, -1):
        path.append(best[i][path[-1]][1])
    path.reverse()

    post, margins, unresolved, sources = [], [], [], []
    for i, s in enumerate(slots):
        if s.locked:
            post.append([(s.locked, 1.0)]); margins.append(1.0); sources.append("user")
            continue
        left = path[i - 1] if i > 0 else None
        right = path[i + 1] if i + 1 < n else None
        cand_names = [g for g, _ in options[i]]
        jb = jargon(cand_names, left, right) if jargon else {}
        scores = []
        for g, lp in options[i]:
            sc = lp + LAMBDA * (_trans(cat_of(left) if left else "^", cat_of(g))
                                + _trans(cat_of(g), cat_of(right) if right else "$"))
            window = [path[j] for j in range(max(0, i - 2), min(n, i + 3)) if j != i]
            sc += MU * sum(1 for w in window if frozenset((w, g)) in COOC)
            if g in hist or any(frozenset((h, g)) in COOC for h in hist):
                sc += HIST
            sc += jb.get(g, 0.0)
            scores.append(sc)
        m = max(scores)
        ps = [math.exp(x - m) for x in scores]
        z = sum(ps)
        ps = [p / z for p in ps]
        order = sorted(range(len(ps)), key=lambda k: -ps[k])
        top = [(options[i][k][0], ps[k]) for k in order]
        post.append(top)
        margin = top[0][1] - (top[1][1] if len(top) > 1 else 0.0)
        margins.append(margin)
        path[i] = top[0][0]
        vis_top = s.cands[0][0]
        if jb.get(top[0][0], 0) > 0.9:
            sources.append("user")
        elif top[0][0] != vis_top:
            sources.append("context")
        else:
            sources.append("lattice")
        if margin < AMBIG_MARGIN and len(top) > 1 and s.kind != "fs":
            unresolved.append(i)
    return Resolved(path, post, margins, unresolved, sources)


# ------------------------------------------------------------------ English realisation
VERBS = {  # base, 3sg, past
    "GO": ("go", "goes", "went"), "COME": ("come", "comes", "came"), "EAT": ("eat", "eats", "ate"),
    "DRINK": ("drink", "drinks", "drank"), "HELP": ("help", "helps", "helped"),
    "WANT": ("want", "wants", "wanted"), "UNDERSTAND": ("understand", "understands", "understood"),
    "WORK": ("work", "works", "worked"), "KNOW": ("know", "knows", "knew"),
    "LIKE": ("like", "likes", "liked"), "NEED": ("need", "needs", "needed"),
    "SIGN": ("sign", "signs", "signed"),
}
SUBJ = {"ME": ("I", "1s"), "YOU": ("you", "2"), "HE-SHE": ("he/she", "3s"), "WE": ("we", "1p"),
        "THEY": ("they", "3p")}
OBJ_PRON = {"ME": "me", "YOU": "you", "HE-SHE": "him/her", "WE": "us", "THEY": "them"}
POSS = {"MY": "my", "YOUR": "your", "HE-SHE": "his/her", "WE": "our", "THEY": "their"}
PERSON_NOUNS = {"MOTHER", "FATHER", "FRIEND", "DOCTOR"}
PLACES = {"BANK": "the bank", "SCHOOL": "school", "HOSPITAL": "the hospital", "TOILET": "the toilet",
          "RIVER": "the river", "HOME": "home"}
NOUNS = {"WATER": "water", "FOOD": "food", "MONEY": "money", "MEDICINE": "medicine", "PAIN": "pain",
         "TIME": "time", "BOOK": "a book", "NAME": "name", "MOTHER": "mother", "FATHER": "father",
         "FRIEND": "friend", "DOCTOR": "doctor", "RIVER": "the river", "BANK": "the bank",
         "SCHOOL": "school", "HOSPITAL": "the hospital", "TOILET": "the toilet", "HOME": "home"}
ADJ = {"GOOD": "good", "BAD": "bad", "HAPPY": "happy", "SAD": "sad", "SICK": "sick"}
TIME_WORD = {"YESTERDAY": "yesterday", "TODAY": "today", "TOMORROW": "tomorrow", "NOW": "now",
             "MORNING": "this morning", "NIGHT": "tonight"}
PHRASE = {"HELLO": "Hello", "THANK-YOU": "Thank you", "PLEASE": "Please", "SORRY": "Sorry",
          "WELCOME": "You're welcome", "YES": "Yes", "NO": "No"}
WH = {"WHAT": "what", "WHERE": "where", "WHEN": "when", "WHO": "who", "WHY": "why", "HOW": "how",
      "HOW-MANY": "how many"}


@dataclass
class Piece:
    text: str
    slots: list[int] = field(default_factory=list)


def _fs_word(g: str) -> str:
    w = g[3:]
    return w[:1].upper() + w[1:].lower() if w else "?"


def _noun_text(g: str) -> str:
    if g.startswith("FS:"):
        return _fs_word(g)
    return NOUNS.get(g) or ADJ.get(g) or g.lower().replace("-", " ")


def _person(subj: Optional[str]) -> str:
    if subj is None:
        return "imp"
    if subj in SUBJ:
        return SUBJ[subj][1]
    return "3s"


def _be(person: str, tense: str) -> str:
    if tense == "past":
        return "was" if person in ("1s", "3s") else "were"
    if tense == "future":
        return "will be"
    return {"1s": "am", "3s": "is"}.get(person, "are")


def _do(person: str, tense: str) -> str:
    if tense == "past":
        return "did"
    if tense == "future":
        return "will"
    return "does" if person == "3s" else "do"


def _verb(v: str, person: str, tense: str, neg: bool) -> str:
    base, s3, past = VERBS[v]
    if neg:
        if tense == "future":
            return f"won't {base}"
        return f"{_do(person, tense)}n't {base}".replace("willn't", "won't")
    if tense == "past":
        return past
    if tense == "future":
        return f"will {base}"
    return s3 if person == "3s" else base


def realize_en(gloss: list[str], question: Optional[str], neg_slots: set[int]) -> tuple[str, list[Piece], dict]:
    """Returns (sentence, pieces, info)."""
    for a, b, txt in (("MORNING", "GOOD", "Good morning"), ("NIGHT", "GOOD", "Good night"),
                      ("GOOD", "MORNING", "Good morning"), ("GOOD", "NIGHT", "Good night")):
        if len(gloss) == 2 and gloss == [a, b]:
            return txt + ".", [(0, len(txt), [0, 1])], {"tense": "present", "question_type": None,
                                                         "negated": False, "speech_act": "backchannel"}
    items = list(enumerate(gloss))
    phrases = [(i, g) for i, g in items if cat_of(g) in ("PHRASE", "AFFIRM") or g == "NO" and len(gloss) == 1]
    rest = [(i, g) for i, g in items if (i, g) not in phrases]
    times = [(i, g) for i, g in rest if cat_of(g) == "TIME"]
    whs = [(i, g) for i, g in rest if cat_of(g) == "WH"]
    verbs = [(i, g) for i, g in rest if g in VERBS]
    finish = [i for i, g in rest if g == "FINISH"]
    nots = [i for i, g in rest if g in ("NOT", "NO") and cat_of(g) == "NEG"]
    core = [(i, g) for i, g in rest if (i, g) not in times + whs + verbs and g not in ("FINISH", "NOT", "NO")]

    neg = bool(nots) or any(i in neg_slots for i, _ in verbs + core)
    neg_ids = nots + [i for i, _ in verbs + core if i in neg_slots]
    tense = "present"
    if any(g in ("YESTERDAY",) for _, g in times) or finish:
        tense = "past"
    elif any(g == "TOMORROW" for _, g in times):
        tense = "future"
    qtype = "wh" if whs else ("yesno" if question == "yesno" else None)

    # subject: first pronoun / person noun before the verb (with possessive attached)
    subj_i, subj_g = None, None
    poss = None
    objs: list[Piece] = []
    k = 0
    verb_pos = verbs[0][0] if verbs else 10 ** 6
    subj_poss = None
    has_pron_subj = any(g in SUBJ for i, g in core if i < verb_pos)
    while k < len(core):
        i, g = core[k]
        nxt = core[k + 1][1] if k + 1 < len(core) else None
        if (subj_g is None and not has_pron_subj and g in ("MY", "YOUR") and nxt in PERSON_NOUNS
                and core[k + 1][0] < verb_pos):
            subj_poss = (i, POSS[g])
            subj_i, subj_g = core[k + 1][0], nxt
            k += 2
            continue
        if (subj_g is None and not has_pron_subj and k == 0 and g.startswith("FS:")
                and len(gloss) > 1 and i < verb_pos):
            subj_i, subj_g = i, g
            k += 1
            continue
        if g in ("MY", "YOUR") or (g in POSS and k + 1 < len(core) and core[k + 1][1] in NOUNS and core[k + 1][1] != "NAME" and g not in SUBJ):
            poss = (i, POSS[g])
            k += 1
            continue
        if subj_g is None and i < verb_pos and (g in SUBJ or g in PERSON_NOUNS) and poss is None:
            subj_i, subj_g = i, g
            k += 1
            continue
        txt = _noun_text(g)
        ids = [i]
        if poss is not None:
            txt = f"{poss[1]} {txt.replace('the ', '').replace('a ', '')}"
            ids = [poss[0], i]
            poss = None
        elif g in PERSON_NOUNS and not g.startswith("FS:"):
            txt = f"the {txt}"
        elif g in SUBJ:
            txt = OBJ_PRON[g]
        objs.append(Piece(txt, ids))
        k += 1
    if poss is not None:                           # dangling possessive: "my" alone -> "mine"
        objs.append(Piece({"my": "mine", "your": "yours"}.get(poss[1], poss[1]), [poss[0]]))

    if subj_g is not None:
        s_txt = SUBJ[subj_g][0] if subj_g in SUBJ else _noun_text(subj_g)
        ids = [subj_i]
        if subj_poss is not None:
            s_txt, ids = f"{subj_poss[1]} {s_txt}", [subj_poss[0], subj_i]
        elif subj_g in PERSON_NOUNS:
            s_txt = f"the {s_txt}"
        subj = Piece(s_txt, ids)
    else:
        subj = None
    if any(g == "PLEASE" for _, g in phrases) and verbs and subj_g in ("ME", "WE") and qtype is None:
        objs.insert(0, Piece(OBJ_PRON[subj_g], [subj_i]))
        subj, subj_g = None, None
    person = _person(subj_g)
    pieces: list[Piece] = []
    sentences: list[list[Piece]] = []

    please_inline = None
    for i, g in phrases:
        if g == "PLEASE" and verbs and subj is None and qtype is None:
            please_inline = Piece("please", [i])
            continue
        sentences.append([Piece(PHRASE.get(g, g.title()), [i])])

    body: list[Piece] = []
    end = "."
    time_front = [Piece(TIME_WORD[g], [i]) for i, g in times if g != "NOW"]
    time_back = [Piece("now", [i]) for i, g in times if g == "NOW"]
    fin_ids = finish

    if rest:
        if qtype == "wh":
            end = "?"
            wi, wg = whs[0]
            wh = Piece(WH[wg].capitalize(), [wi])
            if verbs:
                vi, vg = verbs[0]
                aux = _do(person if subj else "2", tense)
                sp = subj or Piece("you", [])
                if neg:
                    aux += "n't" if aux != "will" else ""
                    aux = aux.replace("willn't", "won't")
                body = [wh, Piece(aux, [vi] + fin_ids + neg_ids), sp, Piece(VERBS[vg][0], [vi])] + objs + time_back + time_front
            else:
                noun_pieces = objs if objs else ([subj] if subj else [])
                if wg == "WHAT" and any(p.text.endswith("name") for p in objs):
                    body = [wh, Piece(_be("3s", tense), [])] + objs
                elif wg == "WHAT" and any(g == "TIME" for _, g in core):
                    body = [Piece("What time", [wi] + [i for i, g in core if g == "TIME"]), Piece("is it", [])]
                elif wg == "HOW-MANY" and objs:
                    body = [Piece("How much" if objs[0].text in ("money", "water", "food", "time", "medicine") else "How many", [wi]), objs[0]]
                elif wg in ("HOW",) and subj and not objs:
                    body = [wh, Piece(_be(person, tense), []), subj] + time_back
                elif wg == "WHO" and subj and not objs:
                    body = [wh, Piece(_be(person, tense), []), subj]
                elif noun_pieces:
                    np_ = noun_pieces[0]
                    pl = "3s"
                    body = [wh, Piece(_be(pl, tense) + (" not" if neg else ""), neg_ids), np_] + noun_pieces[1:] + time_back + time_front
                    if subj and subj not in noun_pieces:
                        body = [wh, Piece(_be(person, tense) + (" not" if neg else ""), neg_ids), subj] + noun_pieces + time_back + time_front
                else:
                    body = [wh]
        elif qtype == "yesno":
            end = "?"
            if verbs:
                vi, vg = verbs[0]
                sp = subj or Piece("you", [])
                aux = _do(person if subj else "2", tense)
                if neg:
                    aux = (aux + "n't").replace("willn't", "won't")
                body = [Piece(aux.capitalize(), [vi] + fin_ids + neg_ids), sp, Piece(VERBS[vg][0], [vi])] + objs + time_back + time_front
            elif subj and objs:
                body = [Piece(_be(person, tense).capitalize() + ("n't" if neg else ""), neg_ids), subj] + [_pred(p) for p in objs] + time_back + time_front
            elif objs:
                body = objs + time_front + time_back
            elif subj:
                body = [subj]
        else:
            if verbs:
                vi, vg = verbs[0]
                vtxt = _verb(vg, person, tense, neg)
                obj_pieces = list(objs)
                if vg in ("GO", "COME") and obj_pieces:
                    first = obj_pieces[0]
                    g_first = gloss[first.slots[-1]]
                    if g_first != "HOME" and cat_of(g_first) in ("NOUN", "PRON") and g_first not in ADJ:
                        obj_pieces[0] = Piece(f"to {first.text}", first.slots)
                body = time_front + ([subj] if subj else []) + [Piece(vtxt, [vi] + fin_ids + neg_ids)] + obj_pieces + time_back
                for extra_i, extra_g in verbs[1:]:
                    body.append(Piece("and " + _verb(extra_g, person, tense, False), [extra_i]))
                if subj is None:
                    body[len(time_front)].text = (_verb(vg, "2", "present", neg) if tense == "present" else vtxt)
            elif subj and objs:
                pred = objs
                first_g = gloss[pred[0].slots[-1]]
                if first_g == "PAIN":
                    verb = ("had" if tense == "past" else "will have" if tense == "future" else "has" if person == "3s" else "have")
                    if neg:
                        verb = {"had": "didn't have", "will have": "won't have"}.get(verb, _do(person, tense) + "n't have")
                    body = time_front + [subj, Piece(verb, neg_ids), Piece("pain", pred[0].slots)] + pred[1:] + time_back
                else:
                    be = _be(person, tense) + (" not" if neg else "")
                    body = time_front + [subj, Piece(be, neg_ids)] + [_pred(p) for p in pred] + time_back
            elif subj and fin_ids:
                body = time_front + [subj, Piece(_be(person, "past") if False else "finished", fin_ids)] + time_back
            elif subj:
                body = time_front + [subj] + time_back
            elif objs:
                # possessive + noun + name/noun: "My name is Priya"
                if len(objs) >= 2 and objs[0].text.endswith("name"):
                    be = _be("3s", tense) + (" not" if neg else "")
                    body = time_front + [objs[0], Piece(be, neg_ids)] + objs[1:] + time_back
                elif len(objs) >= 2 and gloss[objs[-1].slots[-1]] in ADJ:
                    be = _be("3s", tense) + (" not" if neg else "")
                    body = time_front + objs[:-1] + [Piece(be, neg_ids), objs[-1]] + time_back
                else:
                    body = ([Piece("Not", neg_ids)] if neg else []) + time_front + objs + time_back
            elif fin_ids:
                body = [Piece("Done", fin_ids)]
            elif time_front or time_back:
                body = time_front + time_back
            elif nots:
                body = [Piece("No", nots)]
            if fin_ids and not verbs and body and all(fi not in p.slots for p in body for fi in fin_ids):
                body.append(Piece("(done)", fin_ids))
    if body and please_inline is not None:
        body = [please_inline] + body
    if body:
        sentences.append(body + [Piece(end, [])])
    elif sentences and question in ("yesno", "wh"):
        pass

    # stitch
    text = ""
    spans = []
    for sent in sentences:
        if sent[-1].text in (".", "?"):
            words, punct = sent[:-1], sent[-1].text
        else:
            words, punct = sent, "."
        first = True
        start_sentence = len(text) + (1 if text else 0)
        if text:
            text += " "
        for p in words:
            if not p.text:
                continue
            w = p.text
            if first:
                w = w[:1].upper() + w[1:]
                first = False
            else:
                text += " "
            s0 = len(text)
            text += w
            spans.append((s0, len(text), p.slots))
        text += punct
        pieces.extend(words)
    info = {"tense": tense, "question_type": qtype, "negated": neg,
            "speech_act": "question" if qtype else ("backchannel" if gloss and all(cat_of(g) in ("PHRASE", "AFFIRM") for g in gloss) else "statement")}
    return text, spans, info


def _pred(p: Piece) -> Piece:
    if p.text in ("doctor", "friend", "the doctor", "the friend"):
        return Piece("a " + p.text.replace("the ", ""), p.slots)
    return p


# ------------------------------------------------------------------ Hindi realisation [REVIEW]
HI_WORD = {
    "ME": "मैं", "YOU": "आप", "HE-SHE": "वह", "WE": "हम", "THEY": "वे", "MY": "मेरा", "YOUR": "आपका",
    "MOTHER": "माँ", "FATHER": "पिता", "FRIEND": "दोस्त", "DOCTOR": "डॉक्टर", "YESTERDAY": "कल",
    "TODAY": "आज", "TOMORROW": "कल", "NOW": "अभी", "MORNING": "सुबह", "NIGHT": "रात", "WATER": "पानी",
    "FOOD": "खाना", "HOME": "घर", "SCHOOL": "स्कूल", "HOSPITAL": "अस्पताल", "BANK": "बैंक", "MONEY": "पैसे",
    "MEDICINE": "दवाई", "PAIN": "दर्द", "TIME": "समय", "BOOK": "किताब", "NAME": "नाम", "RIVER": "नदी",
    "TOILET": "शौचालय", "GOOD": "अच्छा", "BAD": "बुरा", "HAPPY": "खुश", "SAD": "दुखी", "SICK": "बीमार",
    "HELLO": "नमस्ते", "THANK-YOU": "धन्यवाद", "PLEASE": "कृपया", "SORRY": "माफ़ कीजिए", "WELCOME": "स्वागत है",
    "YES": "हाँ", "NO": "नहीं", "WHAT": "क्या", "WHERE": "कहाँ", "WHEN": "कब", "WHO": "कौन", "WHY": "क्यों",
    "HOW": "कैसे", "HOW-MANY": "कितने",
}
HI_VERB = {  # stem, past sg (m), past pl, transitive?
    "GO": ("जा", "गया", "गए", False), "COME": ("आ", "आया", "आए", False), "EAT": ("खा", "खाया", "खाया", True),
    "DRINK": ("पी", "पिया", "पिया", True), "HELP": ("मदद कर", "मदद की", "मदद की", True),
    "WANT": ("चाह", "चाहा", "चाहा", True), "UNDERSTAND": ("समझ", "समझा", "समझे", False),
    "WORK": ("काम कर", "काम किया", "काम किया", True), "KNOW": ("जान", "जाना", "जाना", True),
    "LIKE": ("पसंद कर", "पसंद किया", "पसंद किया", True), "NEED": ("", "", "", False),
    "SIGN": ("साइन कर", "साइन किया", "साइन किया", True),
}
HI_AUX = {"ME": "हूँ", "YOU": "हैं", "HE-SHE": "है", "WE": "हैं", "THEY": "हैं"}
HI_PLURAL = {"YOU", "WE", "THEY"}
HI_ERG = {"ME": "मैंने", "YOU": "आपने", "HE-SHE": "उसने", "WE": "हमने", "THEY": "उन्होंने"}
HI_DAT = {"ME": "मुझे", "YOU": "आपको", "HE-SHE": "उसे", "WE": "हमें", "THEY": "उन्हें"}
HI_FEM = {"MOTHER", "BOOK", "MEDICINE", "RIVER"}
HI_FUT = {"ME": "ऊँगा", "HE-SHE": "एगा", "YOU": "एँगे", "WE": "एँगे", "THEY": "एँगे"}


def realize_hi(gloss: list[str], question: Optional[str], neg_slots: set[int]) -> tuple[str, list, dict]:
    """Rough Hindi (SOV). Masculine singular / respectful plural forms. NEEDS native review."""
    if "PLEASE" in gloss and "HELP" in gloss and gloss.index("HELP") > 0:
        ids = [i for i, g in enumerate(gloss) if g in ("PLEASE", "HELP", "ME")]
        return "कृपया मेरी मदद कीजिए।", [(0, 20, ids)], {"tense": "present", "question_type": None,
                                                        "negated": False, "speech_act": "request"}
    subj = next((g for g in gloss if g in HI_AUX), None)
    noun_subj = subj is None and any(g in PERSON_NOUNS or g.startswith("FS:") for g in gloss)
    tense = "past" if ("YESTERDAY" in gloss or "FINISH" in gloss) else "future" if "TOMORROW" in gloss else "present"
    neg = "NOT" in gloss or bool(neg_slots)
    has_pain = "PAIN" in gloss and not any(g in HI_VERB for g in gloss)
    whs = [i for i, g in enumerate(gloss) if cat_of(g) == "WH"]
    verb_i = next((i for i, g in enumerate(gloss) if g in HI_VERB), None)
    verb_g = gloss[verb_i] if verb_i is not None else None
    modal = verb_g in ("NEED", "WANT") and tense == "present"
    trans_past = verb_g is not None and tense == "past" and HI_VERB[verb_g][3]
    plural = subj in HI_PLURAL
    words: list[tuple[str, list[int]]] = []
    for i, g in enumerate(gloss):
        if g in ("NOT", "FINISH") or i in whs or i == verb_i:
            continue
        w = HI_WORD.get(g) or (g[3:].title() if g.startswith("FS:") else g.lower())
        if g == subj:
            w = HI_DAT[g] if (modal or has_pain) else HI_ERG[g] if trans_past else w
        if g in ("MY", "YOUR") and i + 1 < len(gloss) and gloss[i + 1] in HI_FEM:
            w = w[:-1] + "ी"
        words.append((w, [i]))
    tail: list[tuple[str, list[int]]] = []
    if verb_i is not None:
        stem, psg, ppl, _ = HI_VERB[verb_g]
        if modal:
            v = "चाहिए"
        elif tense == "past":
            v = ppl if plural and not trans_past else psg
        elif tense == "future":
            v = stem + HI_FUT.get(subj or ("HE-SHE" if noun_subj else "YOU"), "एँगे")
        else:
            v = stem + ("ते" if plural else "ता") + " " + HI_AUX.get(subj or "YOU", "हैं")
        if neg:
            v = "नहीं " + v
        tail.append((v, [verb_i]))
    elif len(words) >= 1 and not all(cat_of(g) in ("PHRASE", "AFFIRM") for g in gloss):
        aux = ("है" if has_pain else HI_AUX.get(subj, "है")) if tense == "present" else ("था" if tense == "past" else "होगा")
        tail.append((("नहीं " if neg else "") + aux, []))
    wh_words = [(HI_WORD.get(gloss[i], "क्या"), [i]) for i in whs]
    words = words + wh_words + tail
    if question == "yesno" and not whs:
        words.insert(0, ("क्या", []))
    text, spans = "", []
    for w, ids in words:
        if text:
            text += " "
        s0 = len(text)
        text += w
        spans.append((s0, len(text), ids))
    q = bool(whs) or question == "yesno"
    text += "?" if q else "।"
    return text, spans, {"tense": tense, "question_type": "wh" if whs else question, "negated": neg,
                         "speech_act": "question" if q else "statement"}


def split_clauses(gloss: list[str]) -> list[list[int]]:
    """ISL re-introduces the subject for each clause: 'ME PAIN ME MEDICINE NEED'."""
    clauses, cur, seen_subj = [], [], False
    for i, g in enumerate(gloss):
        if g in SUBJ and seen_subj and any(cat_of(gloss[j]) not in ("PHRASE", "AFFIRM", "TIME") for j in cur[1:]):
            clauses.append(cur)
            cur, seen_subj = [], False
        if g in SUBJ:
            seen_subj = True
        cur.append(i)
    if cur:
        clauses.append(cur)
    return clauses


def realize(gloss, question, neg_slots, lang="en"):
    try:
        return _realize(gloss, question, neg_slots, lang)
    except Exception:                      # never lose the message because a template failed
        words, spans, text = [], [], ""
        for i, g in enumerate(gloss):
            w = _fs_word(g) if g.startswith("FS:") else g.lower().replace("-", " ")
            if text:
                text += " "
            spans.append((len(text), len(text) + len(w), [i]))
            text += w
        text = (text[:1].upper() + text[1:] + ("?" if question else ".")) if text else ""
        return text, spans, {"tense": "present", "question_type": question, "negated": "NOT" in gloss,
                             "speech_act": "question" if question else "statement", "fallback": True}


def _inherit(spans):
    """Function words ("is", "do", "to the") inherit the slots of their neighbour (design rule 4)."""
    out = [list(s) for s in spans]
    for k, sp in enumerate(out):
        if sp[2]:
            continue
        nxt = next((o[2] for o in out[k + 1:] if o[2]), None)
        prv = next((o[2] for o in reversed(out[:k]) if o[2]), None)
        sp[2] = list(nxt or prv or [])
    return [tuple(s) for s in out]


def _realize(gloss, question, neg_slots, lang="en"):
    text, spans, info = _realize_raw(gloss, question, neg_slots, lang)
    return text, _inherit(spans), info


def _realize_raw(gloss, question, neg_slots, lang="en"):
    fn = realize_hi if lang.startswith("hi") else realize_en
    clauses = split_clauses(gloss)
    if len(clauses) <= 1:
        return fn(gloss, question, neg_slots)
    text, spans, info = "", [], None
    for ci, idxs in enumerate(clauses):
        sub = [gloss[i] for i in idxs]
        q = question if ci == len(clauses) - 1 else None
        t, sp, inf = fn(sub, q, {idxs.index(i) for i in neg_slots if i in idxs})
        off = len(text) + (1 if text else 0)
        text = (text + " " + t) if text else t
        spans += [(a + off, b + off, [idxs[k] for k in ids]) for a, b, ids in sp]
        info = inf if info is None else {**info, "question_type": inf["question_type"] or info["question_type"],
                                        "negated": info["negated"] or inf["negated"],
                                        "speech_act": inf["speech_act"] if inf["speech_act"] == "question" else info["speech_act"]}
    return text, spans, info


def high_stakes(gloss: list[str]) -> bool:
    return any(g in HIGH_STAKES for g in gloss)
