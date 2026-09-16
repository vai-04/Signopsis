"""Optional LLM resolver (Qwen3 4B via Ollama). OFF by default.

Enable with:  SIGNOPSIS_RESOLVER=ollama  SIGNOPSIS_OLLAMA_MODEL=qwen3:4b
The LLM is only allowed to *reorder and choose* glosses: its output is
validated against the lexicon and the rule frame, and on any failure
(timeout, bad JSON, unknown gloss, dropped content) we fall back to rules.
The LLM never gets to invent a sign.
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from signopsis.resolve.rules import text_to_frame
from signopsis.resolve.vocab import CATEGORY
from signopsis.schemas import SemanticFrame

GRAMMAR = (Path(__file__).parent / "grammar" / "isl.md").read_text(encoding="utf-8")

PROMPT = """You convert text into Indian Sign Language (ISL) gloss.
Follow these grammar rules exactly:
{grammar}

Allowed glosses: {allowed}
Words with no allowed gloss must be written as FS:WORD (fingerspelling).
A rule-based draft is given; improve ONLY the order or gloss choice.

<text>{text}</text>
<draft>{draft}</draft>

Reply with JSON only: {{"gloss": [...], "question_type": "wh"|"yesno"|null}}"""


def _ollama(prompt: str, timeout: float = 4.0) -> str:
    url = os.getenv("SIGNOPSIS_OLLAMA_URL", "http://localhost:11434/api/generate")
    body = json.dumps({"model": os.getenv("SIGNOPSIS_OLLAMA_MODEL", "qwen3:4b"), "prompt": prompt,
                       "stream": False, "format": "json", "options": {"temperature": 0.1}}).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["response"]


def validate(candidate: list[str], draft: list[str]) -> bool:
    """LLM output must use known glosses and keep the same content (a permutation,
    allowing FINISH to be added/removed)."""
    if not candidate or not all(isinstance(g, str) for g in candidate):
        return False
    for g in candidate:
        if not (g in CATEGORY or g.startswith("FS:")):
            return False
    core = lambda xs: sorted(x for x in xs if x != "FINISH")
    return core(candidate) == core(draft)


def llm_frame(text: str, resolutions: dict[int, str],
              call: Callable[[str], str] = _ollama) -> Optional[SemanticFrame]:
    frame, _ = text_to_frame(text, resolutions)
    if frame.unresolved:          # ambiguity goes to the human, not the LLM
        return frame
    try:
        raw = call(PROMPT.format(grammar=GRAMMAR, allowed=", ".join(sorted(CATEGORY)),
                                 text=text, draft=" ".join(frame.gloss)))
        data = json.loads(raw)
        cand = data.get("gloss", [])
    except Exception:
        return None
    if not validate(cand, frame.gloss):
        return None
    # re-map grounding onto the new order
    old = list(frame.gloss)
    remap = {}
    used = set()
    for ni, g in enumerate(cand):
        for oi, og in enumerate(old):
            if og == g and oi not in used:
                remap[oi] = ni; used.add(oi); break
    for gr in frame.grounding:
        if gr.gloss_index in remap:
            gr.gloss_index = remap[gr.gloss_index]
    frame.gloss = cand
    frame.provenance.resolver = os.getenv("SIGNOPSIS_OLLAMA_MODEL", "qwen3:4b")
    return frame
