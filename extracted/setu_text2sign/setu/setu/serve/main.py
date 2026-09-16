"""FastAPI dev server for pipeline D + the 2D pixel viewer.

    uvicorn setu.serve.main:app --reload          # then open http://localhost:8000
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from setu.generate.avatar2d import frames_json
from setu.generate.signs import LEXICON
from setu.pipeline import text_to_sign
from setu.resolve.vocab import CATEGORY
from setu.schemas import GlossItem, SignTarget

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="SETU text->sign", version="0.1")


class Req(BaseModel):
    text: str
    resolutions: dict[int, str] = {}
    seed: int = 7


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.post("/api/text-to-sign")
def api_text_to_sign(req: Req):
    if len(req.text) > 500:
        raise HTTPException(413, "text too long (500 chars max)")
    return text_to_sign(req.text, req.resolutions, with_frames=True, seed=req.seed)


def sign_clip(gloss: str) -> Optional[dict]:
    if gloss not in LEXICON:
        return None
    return frames_json(SignTarget(gloss=[GlossItem(g=gloss, dur_ms=LEXICON[gloss]["dur"])]))


@app.get("/api/sign/{gloss}")
def api_sign(gloss: str):
    clip = sign_clip(gloss.upper())
    if clip is None:
        raise HTTPException(404, f"no sign for {gloss}")
    return clip


@app.get("/api/lexicon")
def api_lexicon():
    return {"signs": sorted(LEXICON), "vocab_without_sign": sorted(set(CATEGORY) - set(LEXICON))}


@app.get("/healthz")
def health():
    return {"ok": True}
