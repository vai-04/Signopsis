"""Environment variables, thresholds and paths (Section 14)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=False)


def _env(name: str, default: str) -> str:
    # Strip trailing "# comment" left over from .env.example-style lines.
    return os.environ.get(name, default).split("#", 1)[0].strip()


def _path(name: str, default: str) -> Path:
    p = Path(_env(name, default))
    return p if p.is_absolute() else ROOT / p


# Hugging Face / NeMo downloads land under SETU_MODEL_DIR (must be set before
# huggingface_hub is imported anywhere).
os.environ.setdefault("HF_HOME", str(_path("SETU_MODEL_DIR", "data/models") / "hf"))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")


# --- audio front end (Section 6C) ---
SAMPLE_RATE = 16_000
VAD_FRAME_SAMPLES = 512            # Silero expects 512 samples @ 16 kHz (32 ms)
VAD_ON = 0.5                       # speech probability to open a segment
VAD_OFF = 0.35                     # probability below which silence accumulates
MIN_SILENCE_MS = 500               # silence needed to close a segment
MIN_SPEECH_MS = 200                # shorter blips are dropped
PREROLL_MS = 300                   # audio kept before speech onset
MAX_SEGMENT_MS = 20_000            # force-finalize long segments
PARTIAL_INTERVAL_MS = 320          # re-decode cadence for partial captions
FIRST_PARTIAL_MIN_MS = 240         # minimum speech before the first partial
NBEST = 4                          # beam hypotheses for final lattices

# --- trust (Section 5); defaults until eval/ fits real weights ---
TRUST_W_MARGIN = 4.0
TRUST_W_QUALITY = 2.0
TRUST_W_DISAGREE = 3.0
TRUST_BIAS = -1.5
TRUST_TEMPERATURE = 1.0
TRUST_CALIBRATED = False           # flipped once fit_calibration.py writes weights
SLOT_UNCERTAIN_MARGIN = 0.25       # per-word margin below which a span is dotted
UNSEEN_RIVAL_SHARE = 0.5           # share of unassigned word mass treated as one rival
HIGH_STAKES_BUMP = 0.10
PERSONAL_BOOST = 0.05
TRUST_TICK_HZ = 10

# --- text -> sign (Sections 6C/6D) ---
ROUNDTRIP_THRESHOLD = 0.70         # per-gloss read-back probability below which a sign is fingerspelled
ROUNDTRIP_THRESHOLD_HIGH_STAKES = 0.85
ROUNDTRIP_SEED = 7                 # simulated perception noise is seeded: same text -> same plan
SIGN_TEXT_MAX_CHARS = 500
SIGN_CACHE_SIZE = 256              # recent (text, resolutions) plans kept in memory
SIGN_FS_PENALTY = 0.15             # resolver trust lost when every gloss is fingerspelled
SIGN_AMBIGUOUS_TRUST = 0.5         # resolver trust while a lexical ambiguity is open
SIGN_FAST_PACE = 0.85              # duration scale for urgent / fast speech
SIGN_LLM_MIN_GLOSSES = 5           # rules are trusted for shorter plain statements

GATE_PROFILES = {                  # "Ask me when unsure"
    "cautious": (0.85, 0.50),
    "balanced": (None, None),      # None -> SETU_GATE_EMIT / SETU_GATE_REPAIR
    "fluent": (0.65, 0.30),
}


@dataclass(frozen=True)
class Settings:
    host: str = field(default_factory=lambda: _env("SETU_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(_env("SETU_PORT", "8000")))
    llm_url: str = field(default_factory=lambda: _env("SETU_LLM_URL", "http://127.0.0.1:8081"))
    qdrant_url: str = field(default_factory=lambda: _env("SETU_QDRANT_URL", "http://127.0.0.1:6333"))
    vision: str = field(default_factory=lambda: _env("SETU_VISION", "backend"))
    fallback: str = field(default_factory=lambda: _env("SETU_FALLBACK", "off"))
    cloud: str = field(default_factory=lambda: _env("SETU_CLOUD", "off"))
    langfuse: str = field(default_factory=lambda: _env("SETU_LANGFUSE", "off"))
    sign_lang: str = field(default_factory=lambda: _env("SETU_SIGN_LANG", "isl"))
    spoken_langs: tuple[str, ...] = field(
        default_factory=lambda: tuple(s.strip() for s in _env("SETU_SPOKEN_LANGS", "en,hi,ta").split(",") if s.strip())
    )
    gate_emit: float = field(default_factory=lambda: float(_env("SETU_GATE_EMIT", "0.75")))
    gate_repair: float = field(default_factory=lambda: float(_env("SETU_GATE_REPAIR", "0.40")))
    trace_dir: Path = field(default_factory=lambda: _path("SETU_TRACE_DIR", "data/traces"))
    model_dir: Path = field(default_factory=lambda: _path("SETU_MODEL_DIR", "data/models"))
    asr: str = field(default_factory=lambda: _env("SETU_ASR", "parakeet"))
    diarizer: str = field(default_factory=lambda: _env("SETU_DIARIZER", "sortformer"))
    vad: str = field(default_factory=lambda: _env("SETU_VAD", "silero"))
    store_transcripts: bool = field(default_factory=lambda: _env("SETU_STORE_TRANSCRIPTS", "off") == "on")
    sign_output: bool = field(default_factory=lambda: _env("SETU_SIGN_OUTPUT", "on") == "on")
    sign_frames: bool = field(default_factory=lambda: _env("SETU_SIGN_FRAMES", "on") == "on")
    sign_resolver: str = field(default_factory=lambda: _env("SETU_SIGN_RESOLVER", "rules"))
    sign_llm_timeout_s: float = field(default_factory=lambda: float(_env("SETU_SIGN_LLM_TIMEOUT_S", "2.5")))

    @property
    def asr_engine(self) -> str:
        """CPU fallback overrides the GPU engine choice (Section 8)."""
        if self.fallback == "cpu" and self.asr != "fake":
            return "whisper"
        return self.asr

    @property
    def diarizer_engine(self) -> str:
        return "none" if self.fallback == "cpu" else self.diarizer


def get_settings() -> Settings:
    return Settings()


PARAKEET_MODEL = "nvidia/parakeet-tdt-0.6b-v2"
SORTFORMER_MODEL = "nvidia/diar_streaming_sortformer_4spk-v2"
WHISPER_MODEL = "small"
