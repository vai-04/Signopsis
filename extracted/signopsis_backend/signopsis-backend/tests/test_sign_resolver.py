"""L2 trust + L3 sign->text resolution and realisation."""
import json
import random

import pytest

from signopsis.fuse.trust import WEIGHTS_PATH, SlotSignals, TrustModel, gate_for, hold_reason, thresholds
from signopsis.resolve.rules import text_to_frame
from signopsis.resolve.sign_to_text import SlotIn, decode_context, realize, split_clauses
from signopsis.resolve.vocab import CATEGORY


def sig(**kw):
    base = dict(margin=0.9, vis=1.0, overlap=0.0, jitter=0.4, dark=0.0, anchor=1.0, disagreement=0.0, novelty=0.4)
    base.update(kw)
    return SlotSignals(**base)


def test_weights_are_fitted():
    W = json.loads(WEIGHTS_PATH.read_text())
    assert W["fitted"] and W["n_train"] > 100


@pytest.mark.parametrize("field,low,high", [
    ("margin", 0.05, 0.9), ("vis", 0.3, 1.0), ("disagreement", 2.0, 0.0), ("novelty", 1.3, 0.4), ("jitter", 4.5, 0.3),
])
def test_trust_moves_the_right_way(field, low, high):
    tm = TrustModel()
    assert tm.trust(sig(**{field: low})) < tm.trust(sig(**{field: high}))


def test_clean_slot_is_trusted_and_garbage_is_not():
    tm = TrustModel()
    assert tm.trust(sig()) >= 0.75
    assert tm.trust(sig(margin=0.02, vis=0.4, jitter=4, disagreement=2.5, novelty=1.4)) < 0.4


def test_gate_thresholds():
    assert gate_for(0.8) == "emit" and gate_for(0.5) == "repair" and gate_for(0.2) == "hold"
    assert gate_for(0.8, high_stakes=True) == "repair"
    assert thresholds(True) == (0.85, 0.5)


def test_hold_reasons_are_specific():
    assert hold_reason(sig(), lux=20)[0] == "dark"
    assert hold_reason(sig(anchor=0.1), lux=150)[0] == "no_body"
    assert hold_reason(sig(vis=0.3), lux=150)[0] == "hands_lost"
    assert hold_reason(sig(overlap=0.5), lux=150)[0] == "overlap"
    assert hold_reason(sig(novelty=1.5), lux=150)[0] == "unknown"


def slot(*cands, locked=None, kind="sign"):
    return SlotIn(cands=list(cands), percept_id="pe", t=(0, 1), kind=kind, locked=locked)


def test_context_collapses_lattice():
    r = decode_context([slot(("YOU", .99)), slot(("RIVER", .52), ("WATER", .46)), slot(("WANT", .99))])
    assert r.gloss == ["YOU", "WATER", "WANT"] and r.sources[1] == "context" and not r.unresolved


def test_ambiguity_without_context_is_reported():
    r = decode_context([slot(("ME", .99)), slot(("RIVER", .52), ("WATER", .46)), slot(("GO", .99))])
    assert 1 in r.unresolved


def test_jargon_and_lock_decide():
    jar = lambda c, l, r: {"WATER": 1.8} if set(c[:2]) == {"RIVER", "WATER"} else {}
    r = decode_context([slot(("ME", .99)), slot(("RIVER", .52), ("WATER", .46)), slot(("GO", .99))], jargon=jar)
    assert r.gloss[1] == "WATER" and r.sources[1] == "user" and 1 not in r.unresolved
    r = decode_context([slot(("ME", .99)), slot(("RIVER", .52), ("WATER", .46), locked="RIVER"), slot(("GO", .99))])
    assert r.gloss[1] == "RIVER" and r.margins[1] == 1.0


def test_conversation_history_helps():
    r = decode_context([slot(("RIVER", .5), ("WATER", .48))], history=["DRINK"])
    assert r.gloss == ["WATER"]


EN = [
    ("I went to the bank yesterday.", None, "Yesterday I went to the bank."),
    ("What is your name?", None, "What is your name?"),
    ("Do you want water?", "yesno", "Do you want water?"),
    ("I don't understand.", None, "I don't understand."),
    ("My name is Priya.", None, "My name is Priya."),
    ("They went home", None, "They went home."),
    ("Where is the toilet?", None, "Where is the toilet?"),
    ("I have pain, I need medicine.", None, "I have pain. I need medicine."),
    ("Hello, thank you", None, "Hello. Thank you."),
    ("My mother is sick", None, "My mother is sick."),
    ("Are you sick?", "yesno", "Are you sick?"),
    ("Tomorrow I will go to school", None, "Tomorrow I will go to school."),
    ("Help me please", None, "Please help me."),
    ("How are you?", None, "How are you?"),
    ("My friend is coming tomorrow", None, "Tomorrow my friend will come."),
    ("I didn't go to school yesterday", None, "Yesterday I didn't go to school."),
    ("Where do you work?", None, "Where do you work?"),
    ("My father is a doctor", None, "My father is a doctor."),
    ("Priya is my friend", None, "Priya is my friend."),
    ("Good morning", None, "Good morning."),
]


@pytest.mark.parametrize("src,face,expected", EN)
def test_gloss_to_english(src, face, expected):
    gloss = text_to_frame(src)[0].gloss
    text, spans, info = realize(gloss, face, set())
    assert text == expected


def test_head_shake_negates_without_not_sign():
    text, _, info = realize(["ME", "UNDERSTAND"], None, {1})
    assert text == "I don't understand." and info["negated"]


def test_face_turns_statement_into_question():
    assert realize(["YOU", "SICK"], "yesno", set())[0] == "Are you sick?"
    assert realize(["YOU", "SICK"], None, set())[0] == "You are sick."


@pytest.mark.parametrize("gloss,expected", [
    (["YESTERDAY", "ME", "BANK", "GO"], "कल मैं बैंक गया।"),
    (["YOUR", "NAME", "WHAT"], "आपका नाम क्या है?"),
    (["ME", "FOOD", "EAT", "FINISH"], "मैंने खाना खाया।"),
    (["ME", "MONEY", "WANT"], "मुझे पैसे चाहिए।"),
])
def test_gloss_to_hindi(gloss, expected):
    assert realize(gloss, None, set(), "hi")[0] == expected


def test_grounding_spans_point_at_slots():
    gloss = ["YESTERDAY", "ME", "BANK", "GO"]
    text, spans, _ = realize(gloss, None, set())
    words = {text[a:b]: ids for a, b, ids in spans}
    assert words["Yesterday"] == [0] and words["I"] == [1] and words["went"] == [3] and 2 in words["to the bank"]
    assert split_clauses(["ME", "PAIN", "ME", "MEDICINE", "NEED"]) == [[0, 1], [2, 3, 4]]


def test_realiser_never_crashes():
    G = list(CATEGORY) + ["FS:RAVI", "?"]
    rnd = random.Random(0)
    for _ in range(3000):
        g = [rnd.choice(G) for _ in range(rnd.randint(1, 7))]
        for lang in ("en", "hi"):
            text, spans, _ = realize(g, rnd.choice([None, "wh", "yesno"]), set(), lang)
            assert isinstance(text, str)
            assert all(0 <= a <= b <= len(text) and all(0 <= k < len(g) for k in ids) for a, b, ids in spans)
