"""L0/L1: landmark normalisation, handedness, phrase tracking, recognition, non-manuals."""
import numpy as np
import pytest

from setu.generate.avatar2d import frames_json
from setu.generate.signs import LEXICON
from setu.perceive.landmarks import Normalizer
from setu.perceive.nonmanual import Baseline, analyse
from setu.perceive.recognizer import Index, Proto, base_prototypes, noise_level
from setu.perceive.segment import PhraseTracker, decode_phrase, prepare
from setu.perceive.simcam import Degrade, plan_for, stream, text_stream
from setu.schemas import WireFrame


def observe(frames, dominant="right"):
    norm = Normalizer(dominant=dominant)
    return [norm(WireFrame.model_validate(f)) for f in frames]


@pytest.mark.parametrize("deg", [
    Degrade(noise=0.0),
    Degrade(noise=0.0, mirrored=True),
    Degrade(noise=0.0, body_scale=0.8, body_dx=0.08, body_dy=-0.04),
    Degrade(noise=0.0, lefty=True),
])
def test_normalizer_inverts_camera(deg):
    tgt = plan_for(["YESTERDAY", "ME", "BANK", "GO"])
    truth = frames_json(tgt)["frames"]
    obs = observe(stream(tgt, deg, seed=0), dominant="left" if deg.lefty else "right")
    errs = []
    for o, f in zip(obs, truth):
        if f["gi"] >= 0 and o.R is not None:
            errs.append(np.abs(o.R - np.array(f["R"])).max())
    assert len(errs) > 30
    assert max(errs) < 0.6, max(errs)      # signing-space units (the avatar is 100 wide)


def test_crossing_hands_keep_their_identity():
    tgt = plan_for(["PAIN"])                 # both index fingers tap and cross the midline
    truth = frames_json(tgt)["frames"]
    obs = observe(stream(tgt, Degrade(noise=0.3), seed=1))
    for o, f in zip(obs, truth):
        if f["gi"] == 0 and o.R is not None and o.L is not None:
            assert np.linalg.norm(o.R[0] - f["R"][0]) < 3
            assert np.linalg.norm(o.L[0] - f["L"][0]) < 3


def test_handedness_falls_back_to_label_without_pose():
    frames = stream(plan_for(["HELLO"]), Degrade(noise=0.0), seed=0)
    for f in frames:
        f["pose"] = None
    obs = observe(frames)
    truth = frames_json(plan_for(["HELLO"]))["frames"]
    # without shoulders the scale is a guess, but sides must still be right (HELLO is at the signer's right)
    hits = [o.R[0, 0] < 50 for o, t in zip(obs, truth) if o.R is not None and t["gi"] == 0]
    assert hits and np.mean(hits) > 0.9
    assert not any(o.anchor_ok for o in obs)           # no shoulders -> anchor flagged


def test_phrase_tracker_splits_on_rest():
    a = stream(plan_for(["HELLO"]), Degrade(), seed=0)
    b = stream(plan_for(["THANK-YOU"]), Degrade(), seed=1, t0=a[-1]["t"] + 50)
    tr = PhraseTracker()
    norm = Normalizer()
    phrases = [p for p in (tr.push(norm(WireFrame.model_validate(f))) for f in a + b) if p]
    last = tr.flush()
    phrases += [last] if last else []
    assert len(phrases) == 2


def test_base_index_recognises_itself():
    idx = Index()
    T = np.stack([p.T for p in base_prototypes()])
    LD = idx.label_distances(T, np.array([p.dur_ms for p in base_prototypes()]))
    top = [idx.labels[i] for i in LD.argmin(1)]
    assert top == [p.label for p in base_prototypes()]


def test_shortlist_matches_exhaustive_search():
    idx = Index()
    rng = np.random.default_rng(0)
    Q = idx.T[rng.integers(0, len(idx.T), 60)] + rng.normal(0, 0.05, (60,) + idx.T.shape[1:])
    np.testing.assert_array_equal(idx.label_distances(Q, shortlist=0).argmin(1),
                                  idx.label_distances(Q, shortlist=10).argmin(1))


def test_user_prototypes_win_ties():
    base = list(base_prototypes())
    hello = next(p for p in base if p.label == "HELLO")
    idx = Index(base + [Proto("FS:PRIYA", "sign", hello.T.copy(), hello.dur_ms, owner="u")])
    LD = idx.label_distances(hello.T[None])
    assert idx.labels[LD.argmin()] == "FS:PRIYA"


def test_noise_estimate_tracks_jitter():
    tgt = plan_for(["HELLO", "FRIEND"])
    est = []
    for sd in (0.2, 1.0, 2.5):
        P = prepare([o for o in observe(stream(tgt, Degrade(noise=sd), seed=2)) if o.R is not None])
        est.append(P.noise)
    assert est[0] < est[1] < est[2]


@pytest.mark.parametrize("text", ["I went to the bank yesterday.", "What is your name?", "I don't understand.",
                                  "My name is Priya.", "Hello, thank you"])
def test_decoder_reads_clean_signing(text):
    frames, info = text_stream(text, Degrade(noise=0.4), seed=3)
    obs = observe(frames)
    tr = PhraseTracker()
    phrase = next((p for p in (tr.push(o) for o in obs) if p), None) or tr.flush()
    segs = decode_phrase(prepare(phrase), Index())
    words, cur = [], ""
    for s in segs:
        if s.kind == "letter":
            cur += s.labels[0][0]
            continue
        if cur:
            words.append("FS:" + cur); cur = ""
        words.append(s.labels[0][0])
    if cur:
        words.append("FS:" + cur)
    assert words == info["signed"]


def _nm(text, **kw):
    frames, info = text_stream(text, Degrade(**kw), seed=1)
    tr = PhraseTracker()
    obs = observe(frames)
    phrase = next((p for p in (tr.push(o) for o in obs) if p), None) or tr.flush()
    return analyse(phrase, Baseline())


def test_face_grammar():
    assert _nm("Do you want water?").question == "yesno"
    assert _nm("What is your name?").question == "wh"
    assert _nm("I went to the bank yesterday.").question is None
    neg = _nm("I don't understand.")
    assert neg.shake_spans and neg.phrase.head == "shake"


def test_no_phantom_head_shake_in_noise():
    shakes = sum(bool(_nm("I went to the bank yesterday.", noise=3.5, dropout=0.3).shake_spans) for _ in range(3))
    assert shakes == 0
