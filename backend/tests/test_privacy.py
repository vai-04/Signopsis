"""Section 15: no code path writes audio/frames to disk; traces carry no text unless enabled."""

import json

import numpy as np
from fastapi.testclient import TestClient

from setu.config import Settings

from .conftest import silence, tone
from .test_ws_session import chunks, collect_until

MEDIA_EXT = {".wav", ".pcm", ".raw", ".flac", ".mp3", ".ogg", ".webm", ".jpg", ".jpeg", ".png", ".npy", ".npz"}


def test_session_writes_no_media_and_no_text(fake_env):
    from setu.serve.main import create_app

    before = {p for p in fake_env.rglob("*")}
    with TestClient(create_app(Settings())) as client, client.websocket_connect("/ws/session") as ws:
        ws.send_text(json.dumps({"type": "session.start"}))
        collect_until(ws, {"session.ready"})
        for c in chunks(np.concatenate([tone(1.0), silence(0.9)])):
            ws.send_text(json.dumps(c))
        collect_until(ws, {"caption.final", "repair.request", "hold"})
        ws.send_text(json.dumps({"type": "session.end"}))

    new = {p for p in fake_env.rglob("*")} - before
    assert not [p for p in new if p.suffix.lower() in MEDIA_EXT]
    traces = [p for p in new if p.suffix == ".jsonl"]
    assert traces
    for line in traces[0].read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        assert "text" not in rec and "utterance" not in rec
