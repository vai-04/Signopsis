"""SETU server: text -> sign (pipeline D) and live sign -> text (pipelines A/B).

    uvicorn setu.serve.main:app --reload       # open http://localhost:8000

HTTP
  GET  /                         hub
  GET  /sign-to-text             live camera page (MediaPipe runs in the browser)
  GET  /text-to-sign             pixel-avatar page
  POST /api/text-to-sign         {text, resolutions}
  GET  /api/sign/{gloss}         avatar clip for one sign (repair previews)
  GET  /api/lexicon
  GET  /api/simcam               simulated camera stream (no webcam needed)
  GET  /api/users/{u}/signs      taught signs      DELETE .../signs/{label}
  GET  /api/mode   POST /api/mode
WebSocket
  /ws/sign?user=&lang=&dominant= live sign -> text; message contract in setu/perceive/session.py
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from setu.generate.avatar2d import frames_json
from setu.generate.signs import LEXICON, UNLISTED, motion
from setu.memory.store import MemoryStore, safe_user
from setu.perceive.session import SignSession, normalise_label
from setu.perceive.simcam import Degrade, plan_for, stream, text_stream
from setu.pipeline import text_to_sign
from setu.resolve.vocab import CATEGORY
from setu.schemas import GlossItem, SignTarget
from setu.serve.modes import MANAGER

STATIC = Path(__file__).parent / "static"
STORE = MemoryStore()


@asynccontextmanager
async def lifespan(_app):
    await run_in_threadpool(MANAGER.set, "SPEAK")   # load + warm the shared recognizer and round-trip bank
    yield


app = FastAPI(title="SETU", version="0.2", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class Req(BaseModel):
    text: str
    resolutions: dict[int, str] = {}
    seed: int = 7


def _page(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
def hub():
    return _page("hub.html")


@app.get("/text-to-sign", response_class=HTMLResponse)
def page_text_to_sign():
    return _page("index.html")


@app.get("/sign-to-text", response_class=HTMLResponse)
def page_sign_to_text():
    return _page("sign.html")


@app.post("/api/text-to-sign")
def api_text_to_sign(req: Req):
    if len(req.text) > 500:
        raise HTTPException(413, "text too long (500 chars max)")
    if MANAGER.mode not in ("SPEAK", "CONVERSE"):
        MANAGER.set("SPEAK")
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
    return {"signs": sorted(LEXICON), "vocab_without_sign": sorted(set(CATEGORY) - set(LEXICON)),
            "unlisted_demo_signs": sorted(UNLISTED)}


@app.get("/api/simcam")
def api_simcam(text: str = "", gloss: str = "", severity: float = Query(0.0, ge=0, le=1),
               lefty: bool = False, mirrored: bool = False, seed: int = 0, t0: float = 0.0,
               speed: float = Query(1.0, gt=0.3, le=3)):
    """Simulated MediaPipe stream for a sentence (text) or an explicit gloss list (gloss=A,B,DEMO-NAMESIGN)."""
    import numpy as np
    rng = np.random.default_rng(seed)
    deg = Degrade.random(rng, severity) if severity > 0 else Degrade()
    deg.lefty, deg.mirrored, deg.speed = lefty, mirrored, speed
    if gloss:
        gl = [g.strip().upper() for g in gloss.split(",") if g.strip()]
        bad = [g for g in gl if not g.startswith("FS:") and g not in LEXICON and g not in UNLISTED]
        if bad:
            raise HTTPException(400, f"unknown gloss: {bad}")
        frames = stream(plan_for(gl), deg, seed=seed, t0=t0)
        info = {"signed": gl}
    else:
        if not text.strip() or len(text) > 300:
            raise HTTPException(400, "give text (<=300 chars) or gloss")
        frames, info = text_stream(text, deg, seed=seed, t0=t0)
    for f in frames:
        f.pop("_gi", None)
    return {"frames": frames, "info": info,
            "degrade": {k: round(v, 3) if isinstance(v, float) else v for k, v in deg.__dict__.items()}}


@app.get("/api/users/{user}/signs")
def api_user_signs(user: str):
    return {"user": safe_user(user), "signs": STORE.list_signs(user)}


@app.delete("/api/users/{user}/signs/{label}")
def api_user_forget(user: str, label: str):
    return {"removed": STORE.delete_sign(user, normalise_label(label))}


class ModeReq(BaseModel):
    mode: str


@app.get("/api/mode")
def api_mode():
    return MANAGER.status()


@app.post("/api/mode")
def api_set_mode(req: ModeReq):
    try:
        return MANAGER.set(req.mode)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.websocket("/ws/sign")
async def ws_sign(ws: WebSocket, user: str = "default", lang: str = "en", dominant: str = "right"):
    await ws.accept()
    await run_in_threadpool(MANAGER.set, "WATCH")
    sess = await run_in_threadpool(SignSession, safe_user(user), STORE, None,
                                   lang if lang in ("en", "hi") else "en",
                                   dominant if dominant in ("left", "right") else "right")
    await ws.send_json(sess.hello())
    lock = asyncio.Lock()
    try:
        while True:
            msg = await ws.receive_json()
            if not isinstance(msg, dict):
                await ws.send_json({"type": "error", "message": "expected a JSON object"})
                continue
            items = msg.get("items") if msg.get("type") == "batch" else [msg]
            async with lock:
                for m in items or []:
                    events = await run_in_threadpool(sess.handle, m)
                    for e in events:
                        await ws.send_json(e)
    except WebSocketDisconnect:
        pass


@app.get("/healthz")
def health():
    return {"ok": True, "mode": MANAGER.mode}
