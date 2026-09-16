"""Build a single-file offline demo of the viewer with precomputed results.

    python -m setu.serve.build_demo            # -> dist/setu_text2sign_demo.html
"""
from __future__ import annotations

import json
from pathlib import Path

from setu.pipeline import text_to_sign
from setu.serve.main import STATIC, sign_clip

EXAMPLES = [
    "I went to the bank yesterday.",
    "What is your name?",
    "Do you want water?",
    "I don't understand.",
    "My name is Priya.",
    "mujhe kal bank jaana hai",
    "main kal ghar gaya tha",
    "Where is the toilet?",
    "I have pain, I need medicine.",
    "Thank you! See you tomorrow.",
    "They went home",
    "kya aap ko paani chahiye?",
]


def build(out: Path = Path("dist/setu_text2sign_demo.html")) -> Path:
    results, clips = {}, {}
    for text in EXAMPLES:
        r = text_to_sign(text, with_frames=True)
        results[text] = r
        rep = r["plan"]["repair"]
        if rep and rep["type"] == "disambiguate":
            for o in rep["options"]:
                res = {str(rep["token_index"]): o["gloss"]}
                key = text + "|" + json.dumps(res, separators=(",", ":"))
                results[key] = text_to_sign(text, {rep["token_index"]: o["gloss"]}, with_frames=True)
                clips[o["gloss"]] = sign_clip(o["gloss"])
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    payload = json.dumps({"results": results, "clips": clips}, separators=(",", ":"))
    html = html.replace("<script>\n/* ---", f"<script>window.SETU_DEMO={payload};</script>\n<script>\n/* ---", 1)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    p = build()
    print(p, f"{p.stat().st_size/1e6:.2f} MB")
