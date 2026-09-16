"""2D avatar: landmarks are well-formed and the timeline matches the plan."""
import numpy as np

from signopsis.generate.avatar2d import build_timeline, frames_json, render_offline
from signopsis.generate.hand2d import HANDSHAPES, HandPose, pose_to_landmarks
from signopsis.generate.signs import ALPHABET, LEXICON
from signopsis.resolve.vocab import CATEGORY
from signopsis.schemas import GlossItem, SignTarget


def test_landmark_shape_and_bounds():
    for shape in HANDSHAPES:
        lm = pose_to_landmarks(HandPose.make(shape, "neutral"))
        assert lm.shape == (21, 2)
        assert np.isfinite(lm).all()


def test_handshapes_are_distinct():
    base = {s: pose_to_landmarks(HandPose.make(s, "neutral")) for s in HANDSHAPES}
    names = list(base)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            assert np.abs(base[a] - base[b]).max() > 0.5, (a, b)


def test_left_hand_mirrors_right():
    r = pose_to_landmarks(HandPose.make("L", "neutral", side="R"), "R")
    l = pose_to_landmarks(HandPose.make("L", "neutral", side="L"), "L")
    np.testing.assert_allclose(r[:, 0], 100 - l[:, 0], atol=1e-6)
    np.testing.assert_allclose(r[:, 1], l[:, 1], atol=1e-6)


def test_every_sign_stays_in_frame():
    for g, s in LEXICON.items():
        t, R, L, gidx, _ = render_offline(SignTarget(gloss=[GlossItem(g=g, dur_ms=s["dur"])]))
        for H in (R, L):
            assert H.min() > -5 and H.max() < 105, g


def test_lexicon_covers_vocab_except_known_gaps():
    missing = set(CATEGORY) - set(LEXICON)
    assert missing == {"TOILET"}, missing    # TOILET is left out on purpose: tests auto-fingerspelling


def test_timeline_and_frames():
    tgt = SignTarget(gloss=[GlossItem(g="ME", dur_ms=380),
                            GlossItem(g="FS:AB", dur_ms=0, fingerspelled=True, fs_fallback="A-B"),
                            GlossItem(g="GO", dur_ms=460)])
    segs, total = build_timeline(tgt)
    assert [s.gloss_index for s in segs] == [0, 1, 1, 2]
    assert [s.letter for s in segs] == [None, "A", "B", None]
    assert all(a.end <= b.start for a, b in zip(segs, segs[1:]))
    fj = frames_json(tgt)
    assert fj["total_ms"] == total
    assert {f["gi"] for f in fj["frames"]} == {-1, 0, 1, 2}
    assert fj["frames"][0]["gi"] == -1 and fj["frames"][-1]["gi"] == -1   # starts and ends at rest


def test_alphabet_complete():
    assert set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") <= set(ALPHABET)
