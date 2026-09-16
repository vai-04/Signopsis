"""HTTP + WebSocket integration (what the browser and other layers talk to)."""
import pytest
from fastapi.testclient import TestClient

import setu.serve.main as main
from setu.memory.store import MemoryStore


def until(ws, kind):
    while True:
        e = ws.receive_json()
        if e["type"] == kind:
            return e


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "STORE", MemoryStore(tmp_path))
    return TestClient(main.app)


def test_pages_and_static(client):
    for path in ("/", "/sign-to-text", "/text-to-sign", "/static/pixel.js", "/static/mp_client.js", "/healthz"):
        assert client.get(path).status_code == 200, path


def test_simcam_endpoint(client):
    r = client.get("/api/simcam", params={"text": "What is your name?", "severity": 0.3, "seed": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["info"]["signed"] == ["YOUR", "NAME", "WHAT"]
    f = body["frames"][20]
    assert set(f) >= {"t", "w", "h", "hands", "pose", "face", "lux", "mirrored"} and "_gi" not in f
    assert client.get("/api/simcam", params={"gloss": "HELLO,NOPE"}).status_code == 400
    assert client.get("/api/simcam").status_code == 400
    assert client.get("/api/simcam", params={"gloss": "MY,NAME,DEMO-NAMESIGN"}).status_code == 200


def test_mode_manager(client):
    s = client.post("/api/mode", json={"mode": "converse"}).json()
    assert s["mode"] == "CONVERSE" and s["fits"] and s["planned_vram_gb"] <= 8
    s = client.post("/api/mode", json={"mode": "SCREEN"}).json()
    assert "sign_recognizer" not in s["resident"] and "resolver" in s["resident"]     # pinned model stays
    assert client.post("/api/mode", json={"mode": "DANCE"}).status_code == 400


def test_websocket_sign_to_text(client):
    frames = client.get("/api/simcam", params={"text": "I went to the bank yesterday.", "seed": 3}).json()["frames"]
    with client.websocket_connect("/ws/sign?user=wsuser&lang=en") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["user"] == "wsuser"
        ws.send_json({"type": "batch", "items": frames + [{"type": "flush"}]})
        got = []
        while True:
            e = ws.receive_json()
            got.append(e)
            if e["type"] == "result":
                break
        assert e["gate"] == "emit" and e["text"] == "Yesterday I went to the bank."
        assert any(x["type"] == "live" for x in got)
        assert client.get("/api/mode").json()["mode"] == "WATCH"
        ws.send_json({"type": "bogus"})
        assert "unknown message" in until(ws, "error")["message"]
        ws.send_json(["not", "an", "object"])
        assert until(ws, "error")["message"] == "expected a JSON object"


def test_websocket_repair_round_trip(client):
    frames = client.get("/api/simcam", params={"gloss": "ME,RIVER,GO", "seed": 0}).json()["frames"]
    with client.websocket_connect("/ws/sign?user=rep") as ws:
        ws.receive_json()
        ws.send_json({"type": "batch", "items": frames + [{"type": "flush"}]})
        while (e := ws.receive_json())["type"] != "result":
            pass
        assert e["gate"] == "repair"
        rep = e["plan"]["repair"]
        clip = client.get(rep["options"][0]["clip"])
        assert clip.status_code == 200 and clip.json()["frames"]
        ws.send_json({"type": "repair_choice", "frame_id": e["plan"]["frame_id"], "slot": rep["slot"], "choice": "WATER"})
        fixed = until(ws, "result")
        assert fixed["gate"] == "emit" and fixed["text"] == "I go to water."
    # the jargon choice was saved for this user
    assert (client.app and main.STORE.jargon_bonus("rep", ["RIVER", "WATER"], "ME", "GO"))


def test_user_sign_api(client):
    assert client.get("/api/users/nobody/signs").json()["signs"] == []
    assert client.delete("/api/users/nobody/signs/Priya").json()["removed"] == 0
    assert client.get("/api/users/..%2F..%2Fetc/signs").status_code in (200, 404)   # path-safe user ids


def test_text_to_sign_still_works(client):
    r = client.post("/api/text-to-sign", json={"text": "What is your name?"})
    assert r.status_code == 200 and r.json()["plan"]["gate"] == "emit"
