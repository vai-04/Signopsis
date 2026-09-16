"""Medical / legal keyword detector — raises gate thresholds (Section 5)."""

from __future__ import annotations

import re

KEYWORDS = {
    "medical": [
        "allergy", "allergic", "prescription", "dose", "dosage", "mg", "surgery", "diagnosis",
        "blood", "pain", "chest", "breathing", "medicine", "medication", "insulin", "pregnant",
        "emergency", "ambulance", "anesthesia", "overdose", "seizure", "stroke", "heart attack",
    ],
    "legal": [
        "court", "lawyer", "attorney", "contract", "sign here", "consent", "police", "arrest",
        "rights", "testimony", "affidavit", "bail", "custody", "warrant", "lawsuit",
    ],
}

_PATTERNS = {k: re.compile(r"\b(" + "|".join(map(re.escape, v)) + r")\b", re.I) for k, v in KEYWORDS.items()}


def detect(text: str) -> str | None:
    for pack, pat in _PATTERNS.items():
        if pat.search(text):
            return pack
    return None
