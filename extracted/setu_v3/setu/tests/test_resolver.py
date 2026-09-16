"""L3: text -> ISL gloss. Word order and non-manual rules from grammar/isl.md."""
import pytest

from setu.resolve.rules import text_to_frame


def gloss(t, res=None):
    return text_to_frame(t, res)[0].gloss


@pytest.mark.parametrize("text,expected", [
    ("I went to the bank yesterday.", ["YESTERDAY", "ME", "BANK", "GO"]),        # rule 1: time first, verb last
    ("What is your name?", ["YOUR", "NAME", "WHAT"]),                           # rule 3: wh last
    ("Where is the hospital?", ["HOSPITAL", "WHERE"]),
    ("I don't understand", ["ME", "UNDERSTAND", "NOT"]),                        # rule 5: NOT after verb
    ("Do you want water?", ["YOU", "WATER", "WANT"]),                           # rule 2: drop aux
    ("I ate food", ["ME", "FOOD", "EAT", "FINISH"]),                            # rule 6: completive
    ("Thank you so much!", ["THANK-YOU"]),                                      # phrase + dropped intensifiers
    ("main kal ghar gaya tha", ["YESTERDAY", "ME", "HOME", "GO"]),              # Hinglish + tense resolves kal
    ("kal bank jaunga", ["TOMORROW", "BANK", "GO"]),
    ("मैं कल घर गया था", ["YESTERDAY", "ME", "HOME", "GO"]),                     # Devanagari
    ("aapka naam kya hai?", ["YOUR", "NAME", "WHAT"]),
])
def test_word_order(text, expected):
    assert gloss(text) == expected


def test_no_reordering_across_clauses():
    # rule 10: "Help!" stays in its own clause
    assert gloss("Help! I need a doctor now!") == ["HELP", "NOW", "ME", "DOCTOR", "NEED"]


def test_proper_noun_fingerspelled():
    f, _ = text_to_frame("My name is Priya")
    assert f.gloss == ["MY", "NAME", "FS:PRIYA"]
    assert f.entities[0].resolved_from == "fingerspell"


def test_question_types_and_negation():
    assert text_to_frame("What is your name?")[0].question_type == "wh"
    assert text_to_frame("Do you want water?")[0].question_type == "yesno"
    assert text_to_frame("kya aap ko paani chahiye?")[0].question_type == "yesno"   # kya = particle here
    f = text_to_frame("I don't understand")[0]
    assert f.negated and f.question_type is None


def test_language_id():
    assert text_to_frame("I went home")[0].lang == "en"
    assert text_to_frame("main ghar gaya")[0].lang == "hi"
    assert text_to_frame("mujhe kal bank jaana hai")[0].lang in ("hi", "hi-en")


def test_ambiguity_is_not_guessed():
    """Rule 9: 'kal' without tense -> unresolved, never silently collapsed."""
    f, _ = text_to_frame("mujhe kal bank jaana hai")
    assert len(f.unresolved) == 1
    u = f.unresolved[0]
    assert set(u.cands) == {"YESTERDAY", "TOMORROW"}
    assert f.trust < 0.75
    # the author's tap resolves it
    f2, _ = text_to_frame("mujhe kal bank jaana hai", {u.token_index: "TOMORROW"})
    assert not f2.unresolved and f2.gloss[0] == "TOMORROW"
    assert f2.entities[0].resolved_from == "user"


def test_grounding_covers_every_gloss():
    """Design rule 4: every output gloss points back at a source span."""
    text = "I went to the bank yesterday."
    f, pe = text_to_frame(text)
    idx = {g.gloss_index for g in f.grounding}
    assert idx == set(range(len(f.gloss)))
    for g in f.grounding:
        assert g.percept_ids == [pe.id]
        a, b = g.span
        assert 0 <= a < b <= len(text)
    spans = {f.gloss[g.gloss_index]: text[g.span[0]:g.span[1]] for g in f.grounding}
    assert spans["BANK"] == "bank" and spans["YESTERDAY"] == "yesterday"


def test_high_stakes_flag():
    assert text_to_frame("I need medicine")[0].high_stakes
    assert text_to_frame("call the police")[0].high_stakes
    assert not text_to_frame("I like books")[0].high_stakes


def test_empty_and_garbage():
    assert gloss("") == []
    assert gloss("?!") == []
