"""Silero VAD (CPU) + a streaming speech segmenter.

Audio stays in memory: segments are numpy arrays handed to ASR and dropped.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import numpy as np

from ... import config
from ...schemas import new_id


class SileroVAD:
    """Stateful per-session wrapper around the Silero JIT model."""

    _model = None

    def __init__(self) -> None:
        import torch
        from silero_vad import load_silero_vad

        torch.set_num_threads(1)
        if SileroVAD._model is None:
            SileroVAD._model = load_silero_vad()
        self._torch = torch
        self.model = SileroVAD._model
        self.model.reset_states()

    def prob(self, frame: np.ndarray) -> float:
        with self._torch.inference_mode():
            return float(self.model(self._torch.from_numpy(frame), config.SAMPLE_RATE).item())

    def reset(self) -> None:
        self.model.reset_states()


class EnergyVAD:
    """Model-free VAD for tests and the fake pipeline."""

    def __init__(self, on_db: float = -35.0, off_db: float = -45.0) -> None:
        self.on_db, self.off_db = on_db, off_db

    def prob(self, frame: np.ndarray) -> float:
        db = 10 * math.log10(float(np.mean(frame**2)) + 1e-10)
        return float(np.clip((db - self.off_db) / (self.on_db - self.off_db), 0.0, 1.0))

    def reset(self) -> None:
        pass


def make_vad(kind: str):
    return SileroVAD() if kind == "silero" else EnergyVAD()


@dataclass
class SegEvent:
    kind: str                         # "start" | "update" | "end"
    seg_id: str
    start_sample: int                 # absolute sample index in the session stream
    end_sample: int
    audio: np.ndarray | None = None   # whole segment so far (update/end)
    snr_db: float | None = None
    forced: bool = False              # end caused by MAX_SEGMENT_MS


class VADSegmenter:
    def __init__(self, vad, sr: int = config.SAMPLE_RATE) -> None:
        self.vad = vad
        self.sr = sr
        self.frame = config.VAD_FRAME_SAMPLES
        self._pending = np.zeros(0, dtype=np.float32)
        self._preroll: deque[np.ndarray] = deque(maxlen=max(1, config.PREROLL_MS * sr // 1000 // self.frame))
        self._seg: list[np.ndarray] = []
        self._seg_id: str | None = None
        self._seg_start = 0
        self._speech_frames = 0
        self._silence_frames = 0
        self._samples_seen = 0        # samples consumed by the VAD
        self._noise_pow = 1e-6
        self._speech_pow = 0.0
        self._speech_pow_n = 0
        self.last_prob = 0.0

    @property
    def in_speech(self) -> bool:
        return self._seg_id is not None

    @property
    def current_id(self) -> str | None:
        return self._seg_id

    def _ms(self, frames: int) -> int:
        return frames * self.frame * 1000 // self.sr

    def push(self, audio: np.ndarray) -> list[SegEvent]:
        events: list[SegEvent] = []
        self._pending = np.concatenate([self._pending, audio.astype(np.float32, copy=False)])
        n = len(self._pending) // self.frame
        for i in range(n):
            fr = self._pending[i * self.frame:(i + 1) * self.frame]
            p = self.vad.prob(fr)
            self.last_prob = p
            power = float(np.mean(fr**2))
            frame_start = self._samples_seen
            self._samples_seen += self.frame
            if self._seg_id is None:
                if p >= config.VAD_ON:
                    self._open(frame_start)
                    self._seg.append(fr.copy())
                    self._speech_frames = 1
                    self._track_speech(power)
                    events.append(SegEvent("start", self._seg_id, self._seg_start, self._samples_seen))
                else:
                    self._noise_pow = 0.95 * self._noise_pow + 0.05 * power
                    self._preroll.append(fr.copy())
                continue

            self._seg.append(fr.copy())
            if p < config.VAD_OFF:
                self._silence_frames += 1
            else:
                self._silence_frames = 0
                self._speech_frames += 1
                self._track_speech(power)

            seg_ms = self._ms(len(self._seg))
            if self._ms(self._silence_frames) >= config.MIN_SILENCE_MS:
                ev = self._close(forced=False)
                if ev:
                    events.append(ev)
            elif seg_ms >= config.MAX_SEGMENT_MS:
                ev = self._close(forced=True)
                if ev:
                    events.append(ev)
        self._pending = self._pending[n * self.frame:]
        if self._seg_id is not None and n:
            events.append(SegEvent("update", self._seg_id, self._seg_start, self._samples_seen,
                                   audio=self.current_audio()))
        return events

    def current_audio(self) -> np.ndarray:
        return np.concatenate(self._seg) if self._seg else np.zeros(0, dtype=np.float32)

    def speech_ms(self) -> int:
        return self._ms(self._speech_frames)

    def flush(self) -> SegEvent | None:
        return self._close(forced=True) if self._seg_id is not None else None

    def _open(self, frame_start: int) -> None:
        pre = list(self._preroll)
        self._preroll.clear()
        self._seg = pre
        self._seg_id = new_id("seg")
        self._seg_start = frame_start - len(pre) * self.frame
        self._silence_frames = 0
        self._speech_pow, self._speech_pow_n = 0.0, 0

    def _track_speech(self, power: float) -> None:
        self._speech_pow += power
        self._speech_pow_n += 1

    def _close(self, forced: bool) -> SegEvent | None:
        seg_id, start = self._seg_id, self._seg_start
        # Trim trailing silence except a short pad.
        keep_silence = min(self._silence_frames, max(1, 200 * self.sr // 1000 // self.frame))
        drop = self._silence_frames - keep_silence
        frames = self._seg[:len(self._seg) - drop] if drop > 0 else self._seg
        audio = np.concatenate(frames) if frames else np.zeros(0, dtype=np.float32)
        speech_ms = self._ms(self._speech_frames)
        speech_pow = self._speech_pow / max(1, self._speech_pow_n)
        snr = 10 * math.log10(max(speech_pow, 1e-10) / max(self._noise_pow, 1e-10))
        self._seg, self._seg_id = [], None
        self._speech_frames = self._silence_frames = 0
        if speech_ms < config.MIN_SPEECH_MS and not forced:
            return SegEvent("end", seg_id, start, start + len(audio), audio=None)  # dropped blip
        return SegEvent("end", seg_id, start, start + len(audio), audio=audio,
                        snr_db=round(snr, 1), forced=forced)
