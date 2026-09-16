"""Streaming Sortformer 4-speaker diarizer (NeMo, GPU).

One shared model; one `SortformerStream` (speaker cache + FIFO state) per
session. Audio is fed incrementally; each step decodes `chunk_len` 80 ms
frames once `chunk_right_context` frames of lookahead exist. Speakers are
indexed in arrival order, so index 0 is the first person who spoke.
Uses the model card's "ultra low latency" setting (0.32 s input buffer).
"""

from __future__ import annotations

import logging
import threading

import numpy as np

from ... import config

log = logging.getLogger("setu.sortformer")

HOP = 160                   # feature hop (10 ms)
FEAT_PAD = 50               # extra feature frames of audio context before a window
FEAT_PAD_RIGHT = 2          # STFT needs only a few frames after it (adds no real latency)
STREAMING = {"chunk_len": 3, "chunk_right_context": 1, "fifo_len": 188,
             "spkcache_update_period": 144, "spkcache_len": 188}
WARMUP_SECONDS = 40
MAX_KEEP_FRAMES =15 * 60 * 1000 // 80   # keep 15 min of speaker probabilities


class SortformerModel:
    def __init__(self, device: str = "cuda") -> None:
        self.device = device
        self.model = None
        self.lock = threading.Lock()

    def load(self) -> None:
        import torch
        from nemo.collections.asr.models import SortformerEncLabelModel

        self.torch = torch
        from .nemo_util import restore

        m = restore(SortformerEncLabelModel, config.SORTFORMER_MODEL, self.device)
        m.eval()
        for k, v in STREAMING.items():
            setattr(m.sortformer_modules, k, v)
        m.sortformer_modules._check_streaming_parameters()
        m.streaming_mode = True
        m.preprocessor.featurizer.dither = 0.0
        m.preprocessor.featurizer.pad_to = 0
        self.model = m
        sm = m.sortformer_modules
        self.sub = sm.subsampling_factor
        self.frame_samples = HOP * self.sub
        self.step_feats = sm.chunk_len * self.sub
        self.rc_feats = sm.chunk_right_context * self.sub
        self.lc_feats = getattr(sm, "chunk_left_context", 0) * self.sub
        self.n_spk = sm.n_spk

    def warmup(self) -> None:
        """Run past the first FIFO overflow / speaker-cache update (~15 s) so
        those code paths are warm before a real session reaches them."""
        from .parakeet import _warmup_speech

        need = WARMUP_SECONDS * config.SAMPLE_RATE
        speech = _warmup_speech()
        if speech is None or len(speech) == 0:
            speech = (0.01 * np.random.default_rng(0).standard_normal(need)).astype(np.float32)
        audio = np.tile(speech, -(-need // len(speech)))[:need]
        s = self.new_stream()
        for i in range(0, len(audio), 1600):
            s.push(audio[i:i + 1600])

    def new_stream(self) -> "SortformerStream":
        return SortformerStream(self)


class SortformerStream:
    frame_ms = 80

    def __init__(self, owner: SortformerModel) -> None:
        self.o = owner
        m = owner.model
        self.state = m.sortformer_modules.init_streaming_state(
            batch_size=1, async_streaming=getattr(m, "async_streaming", False), device=m.device)
        self.total = owner.torch.zeros((1, 0, owner.n_spk), device=m.device)
        self.audio = np.zeros(0, dtype=np.float32)
        self.audio_start = 0          # absolute sample index of self.audio[0]
        self.stt = 0                  # absolute feature frame of the next chunk
        self.preds = np.zeros((0, owner.n_spk), dtype=np.float32)
        self.preds_start = 0          # absolute 80 ms frame index of self.preds[0]
        self._frames_done = 0

    # called on the GPU worker thread
    def push(self, audio: np.ndarray) -> None:
        o, torch = self.o, self.o.torch
        self.audio = np.concatenate([self.audio, audio])
        total_samples = self.audio_start + len(self.audio)
        while True:
            end = self.stt + o.step_feats
            if (end + o.rc_feats + FEAT_PAD_RIGHT) * HOP > total_samples:
                break
            left = min(o.lc_feats, self.stt)
            f0 = max(0, self.stt - left - FEAT_PAD)             # first feature frame of the window
            a0 = f0 * HOP - self.audio_start
            a1 = (end + o.rc_feats + FEAT_PAD_RIGHT) * HOP - self.audio_start
            window = self.audio[max(0, a0):a1]
            with o.lock, torch.inference_mode():
                sig = torch.from_numpy(np.ascontiguousarray(window)).to(o.device).unsqueeze(0)
                feats, _ = o.model.preprocessor(input_signal=sig, length=torch.tensor([sig.shape[1]], device=o.device))
                s = self.stt - left - f0
                chunk = feats[:, :, s:s + left + o.step_feats + o.rc_feats]
                length = torch.tensor([chunk.shape[2]], device=o.device)
                self.state, self.total = o.model.forward_streaming_step(
                    processed_signal=chunk.transpose(1, 2), processed_signal_length=length,
                    streaming_state=self.state, total_preds=self.total,
                    left_offset=left, right_offset=o.rc_feats)
            new = self.total[0, self._frames_done:].float().cpu().numpy()
            self._frames_done = self.total.shape[1]
            self.preds = np.concatenate([self.preds, new])
            self.stt = end
            # total_preds grows forever inside NeMo's API; keep only a small GPU tail.
            if self.total.shape[1] > 256:
                self.total = self.total[:, -64:]
                self._frames_done = self.total.shape[1]
        keep_from = max(0, (self.stt - o.lc_feats - FEAT_PAD) * HOP)
        if keep_from > self.audio_start:
            self.audio = self.audio[keep_from - self.audio_start:]
            self.audio_start = keep_from
        if len(self.preds) > MAX_KEEP_FRAMES:
            cut = len(self.preds) - MAX_KEEP_FRAMES
            self.preds = self.preds[cut:]
            self.preds_start += cut

    def processed_until(self) -> int:
        return (self.preds_start + len(self.preds)) * self.o.frame_samples

    def probs(self, start_sample: int, end_sample: int) -> np.ndarray:
        fs = self.o.frame_samples
        a = max(0, start_sample // fs - self.preds_start)
        b = max(0, -(-end_sample // fs) - self.preds_start)
        return self.preds[a:b]
