"""Specific, human-readable hold reasons (Section 9)."""

from __future__ import annotations

from ..schemas import PerceptEvent

TOO_DARK = "Too dark to read hands"
HANDS_OVERLAP = "Hands overlapped"
FACE_HIDDEN = "Face not visible"
NOISY = "Too much background noise"
NO_WORDS = "I couldn't make out any words"
UNCLEAR_SPEECH = "Speech was unclear — please say that again"

NOISY_SNR_DB = 6.0


def reason_for(event: PerceptEvent) -> str:
    q = event.quality
    if event.channel == "speech":
        if not any(event.top1()):
            return NO_WORDS
        if q.snr_db is not None and q.snr_db < NOISY_SNR_DB:
            return NOISY
        return UNCLEAR_SPEECH
    if q.lux_est is not None and q.lux_est < 0.2:
        return TOO_DARK
    if q.hand_overlap is not None and q.hand_overlap > 0.5:
        return HANDS_OVERLAP
    if q.landmark_vis is not None and q.landmark_vis < 0.4:
        return FACE_HIDDEN
    return UNCLEAR_SPEECH if event.channel == "speech" else "Signing was unclear — please sign that again"
