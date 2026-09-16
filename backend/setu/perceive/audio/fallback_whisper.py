"""CPU fallback ASR: faster-whisper small INT8 (SETU_FALLBACK=cpu)."""

from __future__ import annotations

import numpy as np

from ... import config
from ...config import get_settings
from .base import ASRResult, Hypothesis, Word


class WhisperASR:
    name = "faster-whisper-small"

    def __init__(self) -> None:
        self.model = None
        self.lang = "en"

    def load(self) -> None:
        from faster_whisper import WhisperModel

        root = get_settings().model_dir / "whisper"
        self.model = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8",
                                  download_root=str(root), cpu_threads=8)

    def warmup(self) -> None:
        self.transcribe_partial(np.zeros(config.SAMPLE_RATE, dtype=np.float32))

    def _langs(self) -> str | None:
        langs = get_settings().spoken_langs
        return langs[0] if len(langs) == 1 else None

    def transcribe_partial(self, audio: np.ndarray) -> str:
        segs, _ = self.model.transcribe(audio, beam_size=1, language=self._langs() or self.lang,
                                        condition_on_previous_text=False, without_timestamps=True)
        return " ".join(s.text.strip() for s in segs).strip()

    def transcribe_final(self, audio: np.ndarray) -> ASRResult:
        segs, info = self.model.transcribe(audio, beam_size=5, language=self._langs(), word_timestamps=True,
                                           condition_on_previous_text=False)
        words: list[Word] = []
        logp = 0.0
        for s in segs:
            logp += s.avg_logprob * max(1, len(s.words or []))
            for w in s.words or []:
                words.append(Word(w.word.strip(), int(w.start * 1000), int(w.end * 1000), conf=float(w.probability)))
        words = [w for w in words if w.text]
        self.lang = info.language or self.lang
        # faster-whisper exposes only the best beam; word probabilities carry the uncertainty.
        return ASRResult(hyps=[Hypothesis(words, score=logp)] if words else [], lang=self.lang, source=self.name,
                         extra={"lang_prob": round(float(info.language_probability or 0.0), 3)})
