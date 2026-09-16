"""FastAPI entry point: `uvicorn setu.serve.main:app --app-dir backend`."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse

from ..config import Settings, get_settings
from ..generate.text_to_sign import SIGN_POOL
from ..perceive.audio.pipeline import GPU
from .modes import ModeManager
from .routes_diag import router as diag_router
from .routes_sign import router as sign_router
from .ws_session import session_endpoint

STATIC = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Load + warm up on the same thread that serves GPU work: cuDNN/cuBLAS
        # handles and plan caches are per thread.
        loop = asyncio.get_running_loop()
        sign_warm = loop.run_in_executor(SIGN_POOL, app.state.modes.load_sign)
        await loop.run_in_executor(GPU, app.state.modes.load_listen)
        await sign_warm
        yield

    app = FastAPI(title="SETU", version="0.1.0", lifespan=lifespan)
    app.state.modes = ModeManager(settings)
    app.include_router(diag_router)
    app.include_router(sign_router)

    @app.get("/health")
    def health() -> dict:
        m = app.state.modes
        return {"ok": True, "warming": m.warming, "asr": getattr(m.asr, "name", None), "diarizer": m.diarizer_name,
                "sign_ready": m.sign.ready, "sign_resolver": m.settings.sign_resolver}

    @app.get("/dev/listen", include_in_schema=False)
    def dev_listen() -> FileResponse:
        return FileResponse(STATIC / "listen.html")

    @app.get("/dev/compose", include_in_schema=False)
    def dev_compose() -> FileResponse:
        return FileResponse(STATIC / "compose.html")

    @app.websocket("/ws/session")
    async def ws_session(ws: WebSocket) -> None:
        await session_endpoint(ws, app.state.modes)

    return app


app = create_app()
