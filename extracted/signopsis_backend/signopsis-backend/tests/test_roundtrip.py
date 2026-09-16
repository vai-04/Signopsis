"""Section 07: the round-trip gate."""
import numpy as np

from signopsis.generate import roundtrip as RT
from signopsis.generate.signs import LEXICON
from signopsis.schemas import GlossItem, SignTarget


def plan(*gl):
    return SignTarget(gloss=[GlossItem(g=g, dur_ms=LEXICON[g]["dur"], fs_fallback="-".join(g)) for g in gl])


def test_recognizer_reads_clean_signs():
    rec = RT.Recognizer()
    from signopsis.generate.avatar2d import render_offline
    wrong = []
    for g in LEXICON:
        t, R, L, _, segs = render_offline(plan(g))
        s = segs[0]
        m = (t >= s.start) & (t <= s.end)
        top = rec.classify(R[m], L[m])[0][0]
        if top != g:
            wrong.append((g, top))
    # WATER/RIVER are deliberately near-identical; any winner between them is acceptable
    assert all({a, b} <= {"WATER", "RIVER"} for a, b in wrong), wrong


def test_lattice_is_distribution():
    from signopsis.generate.avatar2d import render_offline
    t, R, L, _, segs = render_offline(plan("BANK"))
    lat = RT.Recognizer().classify(R, L)
    assert len(lat) == 3
    ps = [p for _, p in lat]
    assert ps == sorted(ps, reverse=True) and 0 < sum(ps) <= 1.0001


def test_gate_passes_clear_signs():
    res = RT.roundtrip_gate(plan("YESTERDAY", "ME", "BANK", "GO"))
    assert res.degraded == []
    assert res.score >= 0.85
    assert res.readback == ["YESTERDAY", "ME", "BANK", "GO"]


def test_gate_catches_confusable_sign_and_fingerspells_it():
    tgt = plan("YOU", "WATER", "WANT")
    res = RT.roundtrip_gate(tgt)
    assert res.degraded == [1]
    assert tgt.gloss[1].fingerspelled
    assert res.readback[1] == "WATER"          # the fingerspelling reads back correctly
    assert not tgt.gloss[0].fingerspelled and not tgt.gloss[2].fingerspelled


def test_high_stakes_threshold_is_stricter():
    lenient = RT.roundtrip_gate(plan("THEY", "HOME", "GO"), threshold=RT.THRESHOLD)
    strict = RT.roundtrip_gate(plan("THEY", "HOME", "GO"), threshold=0.95)
    assert len(strict.degraded) >= len(lenient.degraded)
    assert len(strict.degraded) > 0


def test_gate_is_deterministic():
    a = RT.roundtrip_gate(plan("HELLO", "FRIEND"), seed=3)
    b = RT.roundtrip_gate(plan("HELLO", "FRIEND"), seed=3)
    assert a.score == b.score and a.readback == b.readback


def test_noise_lowers_confidence():
    from signopsis.generate.avatar2d import render_offline
    t, R, L, _, _ = render_offline(plan("MOTHER"))
    rng = np.random.default_rng(0)
    rec = RT.Recognizer()
    clean = dict(rec.classify(R, L)).get("MOTHER", 0)
    noisy = np.mean([dict(rec.classify(R + rng.normal(0, 4, R.shape), L + rng.normal(0, 4, L.shape))).get("MOTHER", 0)
                     for _ in range(5)])
    assert noisy < clean
