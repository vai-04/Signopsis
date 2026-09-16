"""Speech -> text -> sign over the WebSocket, end to end with the fake perceiver."""

import json

import numpy as np
from fastapi.testclient import TestClient

from setu.config import Settings

from .conftest import silence, tone
from .test_ws_session import chunks, collect_until


def speak(ws):
    for c in chunks(np.concatenate([tone(1.2), silence(0.9)])):
        ws.send_text(json.dumps(c))


def start(ws, **kw):
    ws.send_text(json.dumps({"type": "session.start", "mode": "LISTEN", **kw}))
    collect_until(ws, {"session.ready"})


def test_speech_to_sign_end_to_end(fake_env):
    from setu.serve.main import create_app

    with TestClient(create_app(Settings())) as client, client.websocket_connect("/ws/session") as ws:
        start(ws)

        # 1) emitted caption -> ISL render plan grounded on the same segment
        speak(ws)
        got = collect_until(ws, {"caption.final"})
        final = got[-1]
        got += collect_until(ws, {"render.plan"})
        rp = got[-1]
        assert rp["origin"] == "speech" and rp["segment_id"] == final["segment_id"]
        assert rp["source_frame_id"] == final["plan"]["frame_id"]
        plan = rp["plan"]
        assert plan["gate"] == "emit"
        sign = next(t for t in plan["targets"] if t["kind"] == "sign")
        assert [g["g"] for g in sign["gloss"][:2]] == ["GOOD", "MORNING"]
        assert rp["frames"]["frames"] and rp["readback"]
        assert all(g["percept_ids"] == [final["percept"]["id"]] for g in rp["frame"]["grounding"])
        stages = {m["stage"] for m in got if m["type"] == "latency"}
        assert {"sign.total", "sign.after_speech_end"} <= stages

        # 2) repair-gated caption is NOT signed until the listener picks a word
        speak(ws)
        got = collect_until(ws, {"repair.request"})
        rep = got[-1]["plan"]
        assert not any(m["type"] == "render.plan" for m in got)
        ws.send_text(json.dumps({"type": "repair.pick", "frame_id": rep["frame_id"], "choice": "there"}))
        fixed = collect_until(ws, {"caption.final"})[-1]
        assert fixed["segment_id"] == got[-1]["segment_id"]
        assert "over there by" in fixed["plan"]["targets"][0]["text"]
        assert fixed["plan"]["targets"][0]["trust_badge"] == "high"
        rp = collect_until(ws, {"render.plan"})[-1]
        assert rp["origin"] == "repair" and rp["plan"]["gate"] == "emit"
        assert "over there by" in rp["frame"]["utterance"]

        # 3) held caption is never signed
        speak(ws)
        got = collect_until(ws, {"hold"})
        ws.send_text(json.dumps({"type": "compose.text", "text": ""}))
        rp = collect_until(ws, {"render.plan"})[-1]
        assert rp["origin"] == "compose" and rp["plan"]["gate"] == "hold"   # only the empty compose came back
        ws.send_text(json.dumps({"type": "session.end"}))


def test_compose_repair_round_trip(fake_env):
    from setu.serve.main import create_app

    with TestClient(create_app(Settings())) as client, client.websocket_connect("/ws/session") as ws:
        # Compose works without session.start (no mic needed)
        ws.send_text(json.dumps({"type": "compose.text", "text": "mujhe kal bank jaana hai"}))
        rp = collect_until(ws, {"render.plan"})[-1]
        plan = rp["plan"]
        assert plan["gate"] == "repair" and plan["repair"]["type"] == "disambiguate"
        ws.send_text(json.dumps({"type": "repair.pick", "frame_id": plan["frame_id"], "choice": "TOMORROW"}))
        rp = collect_until(ws, {"render.plan"})[-1]
        assert rp["origin"] == "repair" and rp["plan"]["gate"] == "emit"
        assert rp["frame"]["gloss"][0] == "TOMORROW"

        # resolutions can also be sent up front
        ws.send_text(json.dumps({"type": "compose.text", "text": "mujhe kal bank jaana hai",
                                 "resolutions": {str(plan["repair"]["token_index"]): "YESTERDAY"}}))
        assert collect_until(ws, {"render.plan"})[-1]["frame"]["gloss"][0] == "YESTERDAY"

        ws.send_text(json.dumps({"type": "compose.text", "text": "hello", "target_sign_lang": "asl"}))
        assert collect_until(ws, {"render.plan"})[-1]["plan"]["gate"] == "hold"
        ws.send_text(json.dumps({"type": "session.end"}))


def test_sign_output_can_be_turned_off(fake_env):
    from setu.serve.main import create_app

    with TestClient(create_app(Settings())) as client, client.websocket_connect("/ws/session") as ws:
        start(ws, sign_output=False)
        speak(ws)
        collect_until(ws, {"caption.final"})
        ws.send_text(json.dumps({"type": "compose.text", "text": "hello", "target_sign_lang": "isl"}))
        got = collect_until(ws, {"render.plan"})
        assert [m["origin"] for m in got if m["type"] == "render.plan"] == ["compose"]
        ws.send_text(json.dumps({"type": "session.end"}))
