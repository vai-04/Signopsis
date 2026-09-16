"""Real-model checks for layer 1. Run with: make test-gpu  (needs models + data/clips)."""

import time
import wave

import numpy as np
import pytest

from setu import config

pytestmark = pytest.mark.gpu
CLIPS = config.ROOT / "data" / "clips"


def load(name):
    path = CLIPS / name
    if not path.exists():
        pytest.skip(f"{path} missing — run backend/scripts/make_test_audio.ps1")
    with wave.open(str(path), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768


@pytest.fixture(scope="module")
def asr():
    from setu.perceive.audio.parakeet import ParakeetASR

    a = ParakeetASR()
    a.load()
    a.warmup()
    return a


def test_parakeet_final_lattice(asr):
    audio = load("one_speaker.wav")[: 16000 * 5]
    res = asr.transcribe_final(audio)
    text = res.text.lower()
    assert "meeting" in text and ("ten" in text or "10" in text)
    assert len(res.hyps) >= 2  # beam alternatives present
    w = res.hyps[0].words
    assert all(x.conf is not None for x in w)
    assert w[-1].end_ms > w[0].start_ms


def test_parakeet_partial_fast(asr):
    audio = load("one_speaker.wav")[: 16000 * 3]
    t = time.perf_counter()
    for _ in range(5):
        asr.transcribe_partial(audio)
    assert (time.perf_counter() - t) / 5 < 0.25


def test_sortformer_two_speakers():
    from setu.perceive.audio.diarize import bind_speaker
    from setu.perceive.audio.sortformer import SortformerModel

    m = SortformerModel()
    m.load()
    s = m.new_stream()
    audio = load("two_speakers.wav")
    for i in range(0, len(audio), 1600):
        s.push(audio[i:i + 1600])
    probs = s.probs(0, len(audio))
    assert probs.shape[1] == 4 and len(probs) > 0
    active = {bind_speaker(probs[i:i + 25])[0] for i in range(0, len(probs) - 25, 25)}
    assert {0, 1} <= active
