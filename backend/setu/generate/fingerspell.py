"""Fingerspelling for words with no (trustworthy) sign (Section 6C/6D).

PLACEHOLDER alphabet: 13 handshapes x 2 orientations, visually distinct in 2D
but NOT the ISL manual alphabet. Replace with captured reference handshapes
before real use. Digits reuse letters with the palm turned in.
"""

from __future__ import annotations

import string
from dataclasses import replace

from .hand2d import HandPose

_FS_SHAPES = ["FIST", "FLAT", "C", "O", "POINT", "V", "Y", "L", "W", "I", "THUMB", "X", "BENT"]
FS_DUR = 280                       # ms per letter
FS_GLIDE = 60                      # ms between letters

ALPHABET: dict[str, list] = {}
for _i, _ch in enumerate(string.ascii_uppercase):
    _p = HandPose.make(_FS_SHAPES[_i % 13], "fs", 0 if _i < 13 else -90)
    ALPHABET[_ch] = [(0.0, _p), (1.0, _p)]
for _d in "0123456789":
    _base = ALPHABET[string.ascii_uppercase[int(_d)]][0][1]
    ALPHABET[_d] = [(0.0, replace(_base, palm=-1.0)), (1.0, replace(_base, palm=-1.0))]


def fs_letters(word: str) -> str:
    """'Priya' -> 'P-R-I-Y-A' (characters outside the alphabet are dropped)."""
    return "-".join(c for c in word.upper() if c in ALPHABET)


def fs_duration(letters: str) -> int:
    n = len([c for c in letters.split("-") if c])
    return n * FS_DUR + max(n - 1, 0) * FS_GLIDE
