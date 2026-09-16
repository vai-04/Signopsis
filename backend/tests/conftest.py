import os

import numpy as np
import pytest

os.environ.setdefault("SETU_ASR", "fake")
os.environ.setdefault("SETU_VAD", "energy")
os.environ.setdefault("SETU_DIARIZER", "none")

SR = 16000


def tone(seconds: float, amp: float = 0.3, freq: float = 220.0) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * SR), dtype=np.float32)


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SETU_ASR", "fake")
    monkeypatch.setenv("SETU_VAD", "energy")
    monkeypatch.setenv("SETU_DIARIZER", "none")
    monkeypatch.setenv("SETU_FALLBACK", "off")
    monkeypatch.setenv("SETU_TRACE_DIR", str(tmp_path / "traces"))
    monkeypatch.setenv("SETU_STORE_TRANSCRIPTS", "off")
    return tmp_path
