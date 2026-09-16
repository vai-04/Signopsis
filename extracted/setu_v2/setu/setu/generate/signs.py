"""Sign lexicon for the 2D test avatar.

IMPORTANT: these motions are PLACEHOLDERS shaped to be visually distinct in
2D. They are loosely ISL-inspired but have NOT been validated by a Deaf
signer. Replace each entry with motion captured from reference ISL video
(e.g. INCLUDE / ISLRTC dictionary) before any real use. The pipeline,
gate and tests do not depend on the specific motions.

A sign = {"dur": ms, "R": [keyframes], "L": [keyframes] | None}
A keyframe = (t in [0,1], HandPose). L=None means the left hand rests.
"""
from __future__ import annotations

import math
import string
from dataclasses import replace

from setu.generate.hand2d import HandPose

P = HandPose.make


def static(shape, loc, rot=0, palm="out", side="R", hold=True):
    p = P(shape, loc, rot, palm, side)
    return [(0.0, p), (1.0, p)]


def move(shape, a, b, rot=0, palm="out", side="R", shape_b=None, rot_b=None, palm_b=None):
    return [(0.0, P(shape, a, rot, palm, side)),
            (1.0, P(shape_b or shape, b, rot if rot_b is None else rot_b, palm_b or palm, side))]


def tap(shape, loc, rot=0, palm="out", side="R", dx=0, dy=4, n=2):
    ks, steps = [], 2 * n
    for i in range(steps + 1):
        off = 1.0 if i % 2 else 0.0
        ks.append((i / steps, P(shape, loc, rot, palm, side, dx * off, dy * off)))
    return ks


def circle(shape, loc, rot=0, palm="out", side="R", r=5, n=8, turns=1.0):
    return [(i / n, P(shape, loc, rot, palm, side,
                      r * math.cos(2 * math.pi * turns * i / n),
                      r * math.sin(2 * math.pi * turns * i / n))) for i in range(n + 1)]


def wiggle(shape, loc, rot=0, palm="out", side="R", amp=18, n=3):
    return [(i / (2 * n), P(shape, loc, rot + (amp if i % 2 else -amp), palm, side))
            for i in range(2 * n + 1)]


def change(shape_a, shape_b, loc, rot=0, palm="out", side="R"):
    return [(0.0, P(shape_a, loc, rot, palm, side)), (0.35, P(shape_a, loc, rot, palm, side)),
            (1.0, P(shape_b, loc, rot, palm, side))]


def S(dur, R, L=None):
    return {"dur": dur, "R": R, "L": L}


LEXICON: dict[str, dict] = {
    # --- pronouns (pointing / indexing)
    "ME":        S(380, tap("POINT", "chest", rot=160, dy=-3)),
    "MY":        S(400, tap("FLAT", "chest_c", rot=-80, dx=2, dy=0)),
    "YOU":       S(380, move("POINT", "neutral", "front_high", rot=15, rot_b=25)),
    "YOUR":      S(420, move("FLAT", "neutral", "front_high", rot=10, palm="out", rot_b=10)),
    "HE-SHE":    S(380, move("POINT", "neutral", "side", rot=60, rot_b=80)),
    "WE":        S(520, move("POINT", "shoulder", "heart", rot=170, rot_b=190)),
    "THEY":      S(560, move("POINT", "front", "far_side", rot=40, rot_b=90)),
    # --- people
    "MOTHER":    S(480, tap("OPEN", "chin", rot=-90, dx=2, dy=0)),
    "FATHER":    S(480, tap("OPEN", "forehead", rot=-90, dx=2, dy=0)),
    "FRIEND":    S(560, circle("X", "front", rot=-90, r=3, n=6),
                          circle("X", "front", rot=-90, side="L", r=3, n=6)),
    "DOCTOR":    S(520, tap("V", (60, 64), rot=-100, dy=2), static("FLAT", "front", rot=-90, side="L")),
    # --- time
    "YESTERDAY": S(460, move("THUMB", "cheek", "ear", rot=-30, rot_b=-70)),
    "TOMORROW":  S(460, move("THUMB", "ear", "cheek", rot=0, rot_b=40)),
    "TODAY":     S(460, move("Y", "front_high", "front", rot=0), move("Y", "front_high", "front", side="L")),
    "NOW":       S(420, move("BENT", "front_high", "neutral"), move("BENT", "front_high", "neutral", side="L")),
    "MORNING":   S(520, move("FLAT", "low", "front_high", rot=-60, rot_b=-10), static("FLAT", "stomach", rot=90, side="L")),
    "NIGHT":     S(520, move("BENT", "front_high", "front", rot=60, palm="in", rot_b=90), static("FLAT", "stomach", rot=90, side="L")),
    "FINISH":    S(420, move("OPEN", "front_high", "side", rot=0, palm="in", palm_b="out"),
                         move("OPEN", "front_high", "side", side="L", palm="in", palm_b="out")),
    "TIME":      S(440, tap("POINT", (60, 60), rot=180, dy=-3), static("FIST", (62, 66), rot=90, side="L")),
    # --- questions (wiggles / flicks)
    "WHAT":      S(480, wiggle("OPEN", "front", rot=0, amp=20), wiggle("OPEN", "front", side="L", amp=20)),
    "WHERE":     S(480, wiggle("POINT", "front_high", rot=0, amp=22)),
    "WHEN":      S(500, circle("POINT", "front", rot=0, r=4, n=6)),
    "WHO":       S(460, circle("POINT", "mouth", rot=0, r=2.5, n=6)),
    "WHY":       S(520, change("FLAT", "Y", "temple", rot=-20)),
    "HOW":       S(520, move("BENT", "front", "front_high", rot=90, palm="in", palm_b="out"),
                         move("BENT", "front", "front_high", side="L", rot=90, palm="in", palm_b="out")),
    "HOW-MANY":  S(560, change("FIST", "OPEN", "front_high", rot=0)),
    # --- negation / affirmation
    "NOT":       S(420, move("FLAT", "center", "side", rot=90, palm="in")),
    "NO":        S(420, wiggle("H", "front_high", rot=0, amp=12, n=2)),
    "YES":       S(420, tap("FIST", "front_high", rot=0, dy=5)),
    # --- verbs
    "GO":        S(460, move("POINT", "chest", "far_side", rot=30, rot_b=75)),
    "COME":      S(460, move("POINT", "far_side", "chest", rot=75, rot_b=150)),
    "EAT":       S(480, tap("O", "mouth", rot=-10, dy=3, dx=2)),
    "DRINK":     S(480, move("C", "chin", "nose", rot=-10, rot_b=-40)),
    "HELP":      S(520, move("THUMB", "stomach", "front_high", rot=0),
                         move("FLAT", "stomach", "front_high", side="L", rot=90)),
    "WANT":      S(500, move("OPEN", "front_high", "chest", rot=0, shape_b="BENT"),
                         move("OPEN", "front_high", "chest", side="L", shape_b="BENT")),
    "UNDERSTAND": S(480, change("FIST", "POINT", "temple", rot=0)),
    "WORK":      S(520, tap("FIST", (50, 58), rot=90, dy=4), static("FIST", (54, 66), rot=90, side="L")),
    "KNOW":      S(440, tap("BENT", "forehead", rot=-30, dx=-2, dy=0)),
    "LIKE":      S(480, move("L", "chest", "front", rot=0, shape_b="O")),
    "NEED":      S(460, tap("X", "front", rot=0, dy=5)),
    "SIGN":      S(560, circle("POINT", "front", rot=0, r=4), circle("POINT", "front", side="L", r=4)),
    # --- nouns
    "WATER":     S(460, tap("W", "chin", rot=0, dx=0, dy=2)),
    "RIVER":     S(460, tap("W", "chin", rot=2, dx=0, dy=2)),   # DELIBERATELY ~identical to WATER: exercises the round-trip gate
    "FOOD":      S(480, move("O", "chest", "mouth", rot=-10), static("FLAT", "stomach", rot=90, side="L")),
    "HOME":      S(520, move("O", "cheek", "chin", rot=0, shape_b="FLAT")),
    "SCHOOL":    S(500, tap("FLAT", (48, 56), rot=90, palm="in", dy=3), static("FLAT", (52, 62), rot=90, side="L")),
    "HOSPITAL":  S(560, move("H", "shoulder", "chest", rot=90, rot_b=0)),
    "BANK":      S(520, tap("C", (56, 58), rot=90, dy=3), static("FLAT", "center", rot=90, side="L")),
    "MONEY":     S(500, tap("O", (54, 56), rot=0, dy=4), static("FLAT", (54, 64), rot=90, side="L")),
    "MEDICINE":  S(520, circle("POINT", (58, 62), rot=180, r=2.5), static("FLAT", (58, 68), rot=90, side="L")),
    "PAIN":      S(520, tap("POINT", "front", rot=90, dx=4, dy=0), tap("POINT", "front", rot=90, side="L", dx=4, dy=0)),
    "BOOK":      S(520, move("FLAT", "center", "neutral", rot=0, palm="in", palm_b="out", rot_b=-30),
                         move("FLAT", "center", "neutral", side="L", palm="in", palm_b="out", rot_b=-30)),
    "NAME":      S(480, tap("H", "front", rot=-90, dy=3), static("H", "front", rot=-90, side="L")),
    # --- adjectives
    "GOOD":      S(420, move("THUMB", "chest", "front", rot=0)),
    "BAD":       S(420, move("THUMB", "front", "low", rot=180, rot_b=180)),
    "HAPPY":     S(520, move("OPEN", "stomach", "chest", rot=-20, palm="in"), move("OPEN", "stomach", "chest", side="L", rot=-20, palm="in")),
    "SAD":       S(520, move("OPEN", "eyes", "chin", rot=0, palm="in"), move("OPEN", "eyes", "chin", side="L", palm="in")),
    "SICK":      S(520, tap("OPEN", "forehead", rot=-60, dy=2)),
    # --- social
    "HELLO":     S(520, wiggle("FLAT", "head_side", rot=0, amp=15, n=2)),
    "THANK-YOU": S(520, move("FLAT", "chin", "front_high", rot=0, rot_b=20, palm="in")),
    "PLEASE":    S(520, circle("FLAT", "heart", rot=-90, palm="in", r=4)),
    "SORRY":     S(520, circle("Y", "heart", rot=-40, r=4)),
    "WELCOME":   S(520, move("FLAT", "side", "chest", rot=60, rot_b=90, palm="in")),
}

# ---- fingerspelling (placeholder alphabet: 13 handshapes x 2 orientations)
_FS_SHAPES = ["FIST", "FLAT", "C", "O", "POINT", "V", "Y", "L", "W", "I", "THUMB", "X", "BENT"]
FS_DUR = 280
ALPHABET: dict[str, list] = {}
for i, ch in enumerate(string.ascii_uppercase):
    shape = _FS_SHAPES[i % 13]
    rot = 0 if i < 13 else -90
    p = P(shape, "fs", rot)
    ALPHABET[ch] = [(0.0, p), (1.0, p)]
for d in "0123456789":   # digits reuse letters with palm-in; placeholder
    base = ALPHABET[string.ascii_uppercase[int(d)]][0][1]
    ALPHABET[d] = [(0.0, replace(base, palm=-1.0)), (1.0, replace(base, palm=-1.0))]


def has_sign(gloss: str) -> bool:
    return gloss in LEXICON


def fs_letters(word: str) -> str:
    return "-".join(c for c in word.upper() if c in ALPHABET)


# ---- signs deliberately NOT in the lexicon or the recognizer's base index.
# Used by the simulator to demo the "unknown sign -> teach me" flow (a name sign).
UNLISTED: dict[str, dict] = {
    "DEMO-NAMESIGN": S(620, wiggle("I", "cheek", rot=-40, amp=25, n=2),
                       static("C", (62, 50), rot=0, side="L")),
    "DEMO-JARGON":   S(640, circle("L", "forehead", rot=-60, r=4, n=8),
                       static("L", (60, 56), rot=-90, side="L")),
}


def motion(gloss: str) -> dict:
    return LEXICON.get(gloss) or UNLISTED[gloss]
