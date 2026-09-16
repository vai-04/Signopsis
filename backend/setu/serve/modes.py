"""Mode manager — owns resident models and reports VRAM (Section 8).

Only LISTEN is implemented so far; other modes report "not built yet".
The text -> sign engine is CPU-only and resident in every mode.
"""

from __future__ import annotations

import logging
import sys
import threading

from ..clock import Stopwatch
from ..config import Settings
from ..generate.text_to_sign import TextToSign
from ..perceive.audio.diarize import NullDiarizer
from ..schemas.ws import ModeState

log = logging.getLogger("setu.modes")

VRAM_WARN_MB = 400
IMPLEMENTED_MODES = {"LISTEN"}


def make_asr(engine: str):
    if engine == "parakeet":
        from ..perceive.audio.parakeet import ParakeetASR
        return ParakeetASR()
    if engine == "whisper":
        from ..perceive.audio.fallback_whisper import WhisperASR
        return WhisperASR()
    if engine == "fake":
        from ..perceive.fake import FakeASR
        return FakeASR()
    raise ValueError(f"unknown SETU_ASR={engine!r}")


def gpu_memory() -> tuple[int | None, int | None, int | None]:
    """(torch allocated MB, nvidia-smi used MB, nvidia-smi free MB)."""
    torch_mb = used = free = None
    if "torch" in sys.modules:
        torch = sys.modules["torch"]
        if torch.cuda.is_available():
            torch_mb = int(torch.cuda.memory_allocated() // 2**20)
    try:
        import pynvml

        pynvml.nvmlInit()
        info = pynvml.nvmlDeviceGetMemoryInfo(pynvml.nvmlDeviceGetHandleByIndex(0))
        used, free = int(info.used // 2**20), int(info.free // 2**20)
    except Exception:
        pass
    return torch_mb, used, free


class ModeManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mode = "LISTEN"
        self.asr = None
        self.diar_model = None
        self.warming = True
        self.load_ms: dict[str, float] = {}
        self._lock = threading.Lock()
        self.sign = TextToSign(settings)

    def load_sign(self) -> None:
        """Blocking: build the round-trip template banks. Run on the sign thread at startup."""
        try:
            ms = self.sign.warmup()
            self.load_ms["sign:rules+roundtrip"] = ms
            log.info("text->sign ready in %.0f ms (resolver=%s)", ms, self.settings.sign_resolver)
        except Exception as e:  # plans are still built lazily on first use
            log.error("text->sign warm-up failed: %r", e)

    def load_listen(self) -> None:
        """Blocking: load + warm up LISTEN models. Run in a thread at startup."""
        with self._lock:
            s = self.settings
            with Stopwatch() as sw:
                asr = make_asr(s.asr_engine)
                asr.load()
                asr.warmup()
            self.load_ms[f"asr:{asr.name}"] = sw.ms
            log.info("ASR %s ready in %.0f ms", asr.name, sw.ms)
            self.asr = asr
            if s.diarizer_engine == "sortformer" and s.asr_engine != "fake":
                from ..perceive.audio.sortformer import SortformerModel

                with Stopwatch() as sw:
                    self.diar_model = SortformerModel()
                    self.diar_model.load()
                    self.diar_model.warmup()
                self.load_ms["diar:sortformer"] = sw.ms
                log.info("Sortformer ready in %.0f ms", sw.ms)
            if s.vad == "silero":
                from ..perceive.audio.vad import SileroVAD

                SileroVAD()  # loads the shared JIT model once
            self.warming = False

    def new_diarizer(self):
        if self.diar_model is None:
            return NullDiarizer()
        return self.diar_model.new_stream()

    @property
    def diarizer_name(self) -> str:
        return "sortformer" if self.diar_model is not None else "none"

    def state(self, requested: str | None = None) -> ModeState:
        torch_mb, used, free = gpu_memory()
        warning = None
        if requested and requested not in IMPLEMENTED_MODES:
            warning = f"{requested} mode is not built yet — staying in {self.mode}"
        elif free is not None and free < VRAM_WARN_MB:
            warning = "GPU memory is almost full — switch to CPU fallback (SETU_FALLBACK=cpu)"
        return ModeState(mode=self.mode, vram_mb=used if used is not None else torch_mb,
                         vram_free_mb=free, cloud=self.settings.cloud != "off",
                         warming=self.warming, warning=warning)
