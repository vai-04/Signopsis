"""JSONL tracing + live latency stats (Section 7).

Traces never contain audio or frames. Caption text is written only when
SETU_STORE_TRANSCRIPTS=on (Section 15).
"""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

TEXT_KEYS = {"text", "utterance", "cands", "options", "gloss", "choice"}


class LatencyStats:
    """Process-wide ring buffer of (wall_time, ms) per stage, for S20."""

    def __init__(self, window_s: float = 30.0, maxlen: int = 2000) -> None:
        self.window_s = window_s
        self._data: dict[str, deque[tuple[float, float]]] = defaultdict(lambda: deque(maxlen=maxlen))
        self._lock = threading.Lock()

    def add(self, stage: str, ms: float) -> None:
        with self._lock:
            self._data[stage].append((time.time(), ms))

    def snapshot(self, window_s: float | None = None) -> dict[str, dict[str, float]]:
        cutoff = time.time() - (window_s or self.window_s)
        out: dict[str, dict[str, float]] = {}
        with self._lock:
            for stage, items in self._data.items():
                vals = sorted(ms for t, ms in items if t >= cutoff)
                if vals:
                    out[stage] = {"n": len(vals), "p50": _pct(vals, 50), "p95": _pct(vals, 95), "last": items[-1][1]}
        return out


def _pct(sorted_vals: list[float], p: float) -> float:
    k = (len(sorted_vals) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return round(sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo), 2)


LATENCY = LatencyStats()


class Tracer:
    def __init__(self, session_id: str, trace_dir: Path, store_text: bool = False) -> None:
        self.session_id = session_id
        self.store_text = store_text
        trace_dir.mkdir(parents=True, exist_ok=True)
        self.path = trace_dir / f"{session_id}.jsonl"
        self._fh = self.path.open("a", encoding="utf-8")
        self._lock = threading.Lock()

    def event(self, kind: str, **fields: Any) -> None:
        if not self.store_text:
            fields = {k: v for k, v in fields.items() if k not in TEXT_KEYS}
        rec = {"ts": round(time.time(), 3), "session": self.session_id, "kind": kind, **fields}
        line = json.dumps(rec, default=str, ensure_ascii=False)
        with self._lock:
            self._fh.write(line + "\n")
            self._fh.flush()

    def latency(self, stage: str, ms: float, t: int | None = None) -> None:
        LATENCY.add(stage, ms)
        self.event("latency", stage=stage, ms=round(ms, 2), t=t)

    def close(self) -> None:
        with self._lock:
            self._fh.close()
