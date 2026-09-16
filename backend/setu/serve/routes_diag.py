"""Diagnostics (S20) — computed values only, never hardcoded."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..fuse.trust import TrustWeights
from ..tracing import LATENCY

router = APIRouter(prefix="/diag", tags=["diagnostics"])


@router.get("/latency")
def latency(window_s: float = 30.0) -> dict:
    return {"window_s": window_s, "stages": LATENCY.snapshot(window_s)}


@router.get("/state")
def state(request: Request) -> dict:
    modes = request.app.state.modes
    return {
        "mode": modes.state().model_dump(),
        "asr": getattr(modes.asr, "name", None),
        "diarizer": modes.diarizer_name,
        "model_load_ms": {k: round(v) for k, v in modes.load_ms.items()},
        "trust": "calibrated" if TrustWeights().calibrated else "uncalibrated",
        "reliability": "not measured yet",
    }
