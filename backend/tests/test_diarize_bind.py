import numpy as np

from setu.perceive.audio.diarize import bind_speaker


def frames(*spk_runs):
    rows = []
    for spk, n in spk_runs:
        r = np.full(4, 0.02, dtype=np.float32)
        r[spk] = 0.9
        rows += [r] * n
    return np.stack(rows)


def test_binds_after_two_agreeing_chunks():
    spk, conf = bind_speaker(frames((1, 8)))
    assert spk == 1 and conf > 0.8


def test_no_bind_on_alternating_chunks():
    p = frames((0, 2), (1, 2), (0, 2), (1, 2))
    assert bind_speaker(p, chunk=2) == (None, 0.0)


def test_too_short_or_silent():
    assert bind_speaker(np.zeros((1, 4), dtype=np.float32))[0] is None
    assert bind_speaker(np.zeros((10, 4), dtype=np.float32))[0] is None


def test_turn_change_picks_dominant():
    spk, _ = bind_speaker(frames((0, 8), (2, 16)))
    assert spk == 2
