"""One monotonic session clock (Section 7)."""

from __future__ import annotations

import time


class SessionClock:
    """Milliseconds since session start, from a monotonic source."""

    def __init__(self) -> None:
        self._origin_ns = time.monotonic_ns()

    def now_ms(self) -> int:
        return (time.monotonic_ns() - self._origin_ns) // 1_000_000

    def since(self, t_ms: int) -> int:
        return self.now_ms() - t_ms


class Stopwatch:
    """Precise stage timer: `with Stopwatch() as sw: ...; sw.ms`."""

    def __enter__(self) -> "Stopwatch":
        self._t = time.perf_counter()
        self.ms = 0.0
        return self

    def __exit__(self, *exc) -> None:
        self.ms = (time.perf_counter() - self._t) * 1000.0
