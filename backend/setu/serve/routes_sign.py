"""Text -> sign over HTTP (pipeline D, S11 Compose) + sign lexicon lookups.

The WebSocket path (`compose.text`, and captions from speech) uses the same
engine; these routes serve Compose previews and the repair reference clips.
"""

from __future__ import annotations

import asyncio
from functools import partial

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import config
from ..generate.avatar2d import frames_json
from ..generate.signs import LEXICON
from ..generate.text_to_sign import SIGN_POOL, safe_run
from ..resolve.isl_vocab import CATEGORY
from ..schemas import GlossToken, SignTarget
from ..schemas.session import AskWhenUnsure, SignLang
from ..tracing import LATENCY

router = APIRouter(prefix="/api", tags=["sign"])


class TextToSignRequest(BaseModel):
    text: str
    resolutions: dict[int, str] = {}   # {token_index: gloss} from a sign repair
    sign_lang: SignLang = "isl"
    ask_when_unsure: AskWhenUnsure = "balanced"
    frames: bool = True                # include avatar landmark frames
    seed: int = Field(default=config.ROUNDTRIP_SEED, ge=0)


@router.post("/text-to-sign")
async def text_to_sign(req: TextToSignRequest, request: Request) -> dict:
    """Returns {"frame": SemanticFrame, "plan": RenderPlan, "readback": [LatticeSlot], "frames": {...}|null}."""
    if len(req.text) > config.SIGN_TEXT_MAX_CHARS:
        raise HTTPException(413, f"Text is too long ({config.SIGN_TEXT_MAX_CHARS} characters max)")
    engine = request.app.state.modes.sign
    run = partial(safe_run, engine, req.text, resolutions=req.resolutions, sign_lang=req.sign_lang,
                  profile=req.ask_when_unsure, with_frames=req.frames, seed=req.seed, speaker_label="You")
    result = await asyncio.get_running_loop().run_in_executor(SIGN_POOL, run)
    for stage, ms in result.plan.timings_ms.items():
        LATENCY.add(stage, ms)
    return result.to_json()


def sign_clip(gloss: str) -> dict | None:
    if gloss not in LEXICON:
        return None
    return frames_json(SignTarget(gloss=[GlossToken(g=gloss, dur_ms=LEXICON[gloss]["dur"])]))


@router.get("/sign/{gloss}")
def sign(gloss: str) -> dict:
    """Reference clip (avatar frames) for one gloss — used by repair option previews."""
    clip = sign_clip(gloss.upper())
    if clip is None:
        raise HTTPException(404, f"No sign for {gloss}")
    return clip


@router.get("/lexicon")
def lexicon() -> dict:
    return {"signs": sorted(LEXICON), "vocab_without_sign": sorted(set(CATEGORY) - set(LEXICON)),
            "note": "Placeholder motions — not validated ISL."}
