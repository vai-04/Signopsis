"""Endpoints and messages added for the SIGNOPSIS web app."""
from fastapi.testclient import TestClient

from signopsis.memory.store import MemoryStore
from signopsis.perceive.session import SignSession
from signopsis.perceive.simcam import Degrade, plan_for, stream
from signopsis.serve.main import app

from conftest import play

CART = {
    "title": "Your cart", "kind": "cart", "total": 2480,
    "items": [{"name": "Cotton kurta", "qty": 1, "price": 1299, "id": "a"},
              {"name": "Steel water bottle", "qty": 1, "price": 549, "id": "b"},
              {"name": "Notebook pack", "qty": 2, "price": 316, "id": "c"}],
    "actions": [{"label": "Checkout", "id": "btn", "where": "bottom right", "primary": True}],
}


def test_screen_describe_overview_items_checkout():
    c = TestClient(app)
    r = c.post("/api/screen/describe", json={"question": "What's happening on this page?", "snapshot": CART}).json()
    assert r["answer"] == "Cart page. Three items, total ₹2,480. Checkout is a button at the bottom right."
    r = c.post("/api/screen/describe", json={"question": "read the items", "snapshot": CART}).json()
    assert r["intent"] == "items" and "2 × Notebook pack, ₹632" in r["answer"]
    r = c.post("/api/screen/describe", json={"question": "", "intent": "checkout", "snapshot": CART}).json()
    assert r["targets"][0]["id"] == "btn" and "won't press it" in r["answer"]


def test_eval_report_and_lexicon_langs():
    c = TestClient(app)
    rep = c.get("/api/eval/report").json()
    assert "reliability_bins" in rep and "by_severity" in rep
    assert c.get("/api/lexicon").json()["sign_langs"] == ["isl"]


def test_text_to_sign_accepts_web_fields():
    c = TestClient(app)
    r = c.post("/api/text-to-sign", json={"text": "Hello", "src_lang": "en", "sign_lang": "asl"}).json()
    assert r["plan"]["gate"] in ("emit", "repair", "hold")
    assert r["sign_lang_fallback"] == {"requested": "asl", "used": "isl"}
    r = c.post("/api/text-to-sign", json={"text": "Hello", "sign_lang": "isl"}).json()
    assert "sign_lang_fallback" not in r


def test_cors_allows_vite_dev_server():
    c = TestClient(app)
    r = c.options("/api/lexicon", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_enroll_undo_and_metadata(tmp_path):
    sess = SignSession("web", MemoryStore(tmp_path))
    ev = sess.handle({"type": "enroll_start", "label": "Priya", "kind": "name", "scope": "team"})
    assert ev[0]["have"] == 0
    t0 = 0.0
    for i in range(2):
        out = play(sess, stream(plan_for(["DEMO-NAMESIGN"]), Degrade(noise=0.3), seed=i, t0=t0))
        t0 += 5000
    assert [e for e in out if e["type"] == "enroll_progress"][-1]["have"] == 2
    undo = sess.handle({"type": "enroll_undo"})[0]
    assert undo["have"] == 1 and undo["undone"]
    for i in range(3):
        out = play(sess, stream(plan_for(["DEMO-NAMESIGN"]), Degrade(noise=0.3), seed=10 + i, t0=t0))
        t0 += 5000
    enrolled = [e for e in out if e["type"] == "enrolled"]
    assert enrolled and enrolled[0]["display"] == "Priya"
    signs = sess.store.list_signs("web")
    assert signs[0]["kind"] == "name" and signs[0]["scope"] == "team"
    assert sess.handle({"type": "enroll_undo"})[0]["type"] == "error"
