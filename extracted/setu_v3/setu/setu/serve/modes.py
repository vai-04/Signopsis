"""Mode manager (architecture section 08).

Directions are mutually exclusive in practice, so GPU residency is decided
per mode. In this CPU build the components are light, but the manager is
real: it tracks what each mode needs, loads components lazily, and reports
the (design-doc) VRAM budget so the GPU build can swap in the heavy models
without touching callers.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

BUDGET_GB = 8.0


@dataclass
class Component:
    name: str
    vram_gb: float
    loader: Callable[[], object]
    obj: Optional[object] = None
    load_ms: float = 0.0
    note: str = ""


def _load_recognizer():
    from setu.perceive.recognizer import base_prototypes
    return base_prototypes()


def _load_roundtrip():
    from setu.generate.roundtrip import template_bank
    return template_bank("sign"), template_bank("letter")


def _load_trust():
    from setu.fuse.trust import TrustModel
    return TrustModel()


COMPONENTS = {
    "resolver": Component("resolver", 3.2, lambda: "rules", note="Qwen3-4B-Q4 in the GPU build; rules here"),
    "embeddings": Component("embeddings", 0.2, lambda: "none", note="bge-small (jargon search) in the GPU build"),
    "landmarks": Component("landmarks", 0.5, lambda: "client", note="MediaPipe runs in the browser/client"),
    "sign_recognizer": Component("sign_recognizer", 0.1, _load_recognizer, note="DTW prototypes (ST-GCN later)"),
    "trust": Component("trust", 0.0, _load_trust),
    "avatar": Component("avatar", 0.3, _load_roundtrip, note="2D avatar + round-trip bank (SMPL-X later)"),
    "tts": Component("tts", 0.3, lambda: "browser", note="Web Speech in the browser; Kokoro-82M in the GPU build"),
    "asr": Component("asr", 2.0, lambda: "not-built", note="Parakeet TDT (pipeline C) - not in this build"),
    "diarization": Component("diarization", 0.8, lambda: "not-built", note="Sortformer - not in this build"),
    "screen_parser": Component("screen_parser", 1.5, lambda: "not-built", note="OmniParser v2 - not in this build"),
}

MODES = {
    "WATCH": ["resolver", "embeddings", "landmarks", "sign_recognizer", "trust", "tts"],
    "SPEAK": ["resolver", "embeddings", "avatar", "sign_recognizer"],
    "CONVERSE": ["resolver", "embeddings", "landmarks", "sign_recognizer", "trust", "avatar", "tts", "asr", "diarization"],
    "LISTEN": ["resolver", "embeddings", "asr", "diarization", "avatar"],
    "SCREEN": ["resolver", "screen_parser", "tts"],
}
PINNED = {"resolver", "embeddings"}


@dataclass
class ModeManager:
    mode: str = "SPEAK"
    lock: threading.Lock = field(default_factory=threading.Lock)
    history: list = field(default_factory=list)

    def set(self, mode: str) -> dict:
        mode = mode.upper()
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode}")
        with self.lock:
            t0 = time.perf_counter()
            want = set(MODES[mode]) | PINNED
            for name, c in COMPONENTS.items():
                if name in want and c.obj is None:
                    s = time.perf_counter()
                    c.obj = c.loader()
                    c.load_ms = (time.perf_counter() - s) * 1000
                elif name not in want and c.obj is not None and name not in PINNED:
                    c.obj = None               # unload: frees VRAM on the GPU build
            prev, self.mode = self.mode, mode
            self.history = (self.history + [(time.time(), prev, mode)])[-20:]
            return {**self.status(), "switch_ms": round((time.perf_counter() - t0) * 1000, 1)}

    def status(self) -> dict:
        resident = [n for n, c in COMPONENTS.items() if c.obj is not None]
        planned = sum(COMPONENTS[n].vram_gb for n in set(MODES[self.mode]) | PINNED)
        return {"mode": self.mode, "resident": resident,
                "planned_vram_gb": round(planned, 2), "budget_gb": BUDGET_GB,
                "fits": planned <= BUDGET_GB,
                "components": {n: {"vram_gb": c.vram_gb, "loaded": c.obj is not None,
                                   "load_ms": round(c.load_ms, 1), "note": c.note} for n, c in COMPONENTS.items()}}


MANAGER = ModeManager()
