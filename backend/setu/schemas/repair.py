"""Repair vocabulary shared by L5 and the UI."""

from __future__ import annotations

from typing import Literal

from .render import Repair, RepairOption

# Specific hold reasons (Section 9). Never a generic "error".
HoldReason = Literal[
    "Too dark to read hands",
    "Hands overlapped",
    "Face not visible",
    "Too much background noise",
    "I couldn't make out any words",
    "Speech was unclear — please say that again",
]

__all__ = ["HoldReason", "Repair", "RepairOption"]
