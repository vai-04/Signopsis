"""End-to-end over the WebSocket with the fake perceiver (no models)."""

import base64
import json

import numpy as np
from fastapi.testclient import TestClient

from setu.config import Settings

from .conftest import silence, tone


def chunks(audio, n=1600):
    for i in range(0, len(audio), n):
        pcm = (np.clip(audio[i:i + n], -1, 1) * 32767).astype("<i2").tobytes()
        yield {"type": "audio.chunk", "seq": i // n, "pcm16_b64": base64.b64encode(pcm).decode(), "t": i // 16}


def collect_until(ws, types, limit=400):
    got = []
    for _ in range(limit):
        m = json.loads(ws.receive_text())
        got.append(m)
        if m["type"] in types:
            return got
    raise AssertionError(f"never saw {types}; got {[g['type'] for g in got]}")


def test_three_gates_over_websocket(fake_env):
    from setu.serve.main import create_app

    app = create_app(Settings())
    with TestClient(app) as client, client.websocket_connect("/ws/session") as ws:
        ws.send_text(json.dumps({"type": "session.start", "mode": "LISTEN"}))
        msgs = collect_until(ws, {"session.ready"})
        assert msgs[-1]["asr"] == "fake"

        finals = []
        for _ in range(3):
            for c in chunks(np.concatenate([tone(1.2), silence(0.9)])):
                ws.send_text(json.dumps(c))
            finals.append(collect_until(ws, {"caption.final", "repair.request", "hold"}))

        types = [f[-1]["type"] for f in finals]
        assert types == ["caption.final", "repair.request", "hold"]
        assert any(m["type"] == "caption.partial" for m in finals[0])
        assert any(m["type"] == "trust.tick" for f in finals for m in f)
        assert any(m["type"] == "latency" and m["stage"] == "caption.first_partial" for m in finals[0])

        emit = finals[0][-1]["plan"]
        assert emit["gate"] == "emit" and emit["targets"][0]["trust_badge"] == "high"
        assert finals[0][-1]["percept"]["lattice"]
        rep = finals[1][-1]["plan"]
        assert rep["repair"]["options"][1]["gloss_or_word"] == "there"
        assert finals[2][-1]["reason"] == "Too much background noise"

        ws.send_text(json.dumps({"type": "repair.pick", "frame_id": rep["frame_id"], "choice": "there"}))
        ws.send_text(json.dumps({"type": "video.frame", "seq": 0, "jpeg_b64": "", "t": 0}))
        collect_until(ws, {"error"})
        ws.send_text(json.dumps({"type": "session.end"}))

    diag = client.get("/diag/latency").json()["stages"]
    assert "asr.final" in diag and "trust_gate" in diag


def test_audio_before_start_is_rejected(fake_env):
    from setu.serve.main import create_app

    with TestClient(create_app(Settings())) as client, client.websocket_connect("/ws/session") as ws:
        ws.send_text(json.dumps(next(chunks(tone(0.1)))))
        assert collect_until(ws, {"error"})[-1]["code"] == "not_started"
