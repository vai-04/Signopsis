import numpy as np

from setu import config
from setu.perceive.audio.vad import EnergyVAD, VADSegmenter

from .conftest import SR, silence, tone


def run(seg, audio, chunk=1600):
    events = []
    for i in range(0, len(audio), chunk):
        events += seg.push(audio[i:i + chunk])
    return events


def test_one_utterance_start_update_end():
    seg = VADSegmenter(EnergyVAD())
    evs = run(seg, np.concatenate([silence(0.5), tone(1.0), silence(1.0)]))
    kinds = [e.kind for e in evs]
    assert kinds[0] == "start" and kinds.count("start") == 1 and kinds.count("end") == 1
    assert "update" in kinds
    end = next(e for e in evs if e.kind == "end")
    dur = len(end.audio) / SR
    assert 1.0 <= dur <= 1.0 + (config.PREROLL_MS + 250) / 1000
    assert end.snr_db is not None and end.snr_db > 20
    assert end.start_sample <= int(0.5 * SR)


def test_two_utterances():
    seg = VADSegmenter(EnergyVAD())
    audio = np.concatenate([tone(0.8), silence(0.8), tone(0.8), silence(0.8)])
    ends = [e for e in run(seg, audio) if e.kind == "end"]
    assert len(ends) == 2 and ends[0].seg_id != ends[1].seg_id


def test_blip_dropped():
    seg = VADSegmenter(EnergyVAD())
    ends = [e for e in run(seg, np.concatenate([tone(0.1), silence(1.0)])) if e.kind == "end"]
    assert len(ends) == 1 and ends[0].audio is None


def test_max_segment_forced():
    seg = VADSegmenter(EnergyVAD())
    ends = [e for e in run(seg, tone(config.MAX_SEGMENT_MS / 1000 + 1.0)) if e.kind == "end"]
    assert ends and ends[0].forced


def test_flush_open_segment():
    seg = VADSegmenter(EnergyVAD())
    run(seg, tone(0.6))
    ev = seg.flush()
    assert ev is not None and ev.kind == "end" and ev.audio is not None
