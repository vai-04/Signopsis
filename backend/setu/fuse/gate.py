"""emit / repair / hold (Section 5)."""

from __future__ import annotations

from dataclasses import dataclass

from .. import config
from ..config import Settings
from ..schemas import Gate


@dataclass(frozen=True)
class Thresholds:
    emit: float
    repair: float


def thresholds(settings: Settings, profile: str = "balanced", high_stakes: bool = False) -> Thresholds:
    emit, repair = config.GATE_PROFILES.get(profile, (None, None))
    emit = settings.gate_emit if emit is None else emit
    repair = settings.gate_repair if repair is None else repair
    if high_stakes:
        emit, repair = emit + config.HIGH_STAKES_BUMP, repair + config.HIGH_STAKES_BUMP
    return Thresholds(min(emit, 0.99), min(repair, 0.98))


def decide(trust: float, th: Thresholds) -> Gate:
    if trust >= th.emit:
        return "emit"
    if trust >= th.repair:
        return "repair"
    return "hold"
