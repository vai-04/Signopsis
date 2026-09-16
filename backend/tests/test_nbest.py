import math

from setu.perceive.audio.base import Hypothesis, Word
from setu.perceive.audio.nbest import hyps_to_lattice


def hyp(text, score, conf=None):
    return Hypothesis([Word(w, i * 100, (i + 1) * 100, conf) for i, w in enumerate(text.split())], score)


def test_single_hypothesis_uses_word_conf():
    lat = hyps_to_lattice([hyp("hello world", 0.0, conf=0.8)], offset_ms=1000)
    assert [s.cands[0].value for s in lat] == ["hello", "world"]
    assert lat[0].cands[0].score == 0.8
    assert (lat[1].t0, lat[1].t1) == (1100, 1200)


def test_substitution_becomes_alternative():
    lat = hyps_to_lattice([hyp("meet me there", 0.0), hyp("meet me their", math.log(0.5))])
    third = lat[2]
    assert [c.value for c in third.cands] == ["there", "their"]
    assert abs(third.cands[0].score - 2 / 3) < 1e-3
    assert lat[0].cands[0].score == 1.0


def test_deletion_and_unequal_replace():
    lat = hyps_to_lattice([hyp("I scream loudly", 0.0), hyp("ice cream loudly", 0.0), hyp("I loudly", -1.0)])
    assert len(lat) == 3
    values0 = {c.value for c in lat[0].cands}
    assert "ice cream" in values0 or "ice" in values0
    assert "" in {c.value for c in lat[1].cands}


def test_punctuation_insensitive_alignment():
    lat = hyps_to_lattice([hyp("Hello, world.", 0.0), hyp("hello world", 0.0)])
    assert all(len(s.cands) == 1 and s.cands[0].score == 1.0 for s in lat)


def test_empty():
    assert hyps_to_lattice([]) == []
    assert hyps_to_lattice([Hypothesis([], 0.0)]) == []
