"""End-to-end pipeline D and the RenderPlan contract."""
import json
import time

from fastapi.testclient import TestClient

from signopsis.pipeline import text_to_sign
from signopsis.resolve.llm import llm_frame, validate
from signopsis.schemas import RenderPlan, SemanticFrame
from signopsis.serve.main import app


def sign_of(out):
    return next(t for t in out["plan"]["targets"] if t["kind"] == "sign")


def test_contracts_validate():
    out = text_to_sign("I went to the bank yesterday.", with_frames=True)
    RenderPlan.model_validate(out["plan"])
    SemanticFrame.model_validate(out["frame"])
    json.dumps(out)   # everything is JSON-able


def test_emit_path():
    out = text_to_sign("I went to the bank yesterday.")
    assert out["plan"]["gate"] == "emit"
    assert sign_of(out)["back_translation"].startswith("yesterday · I · bank · go")
    assert out["plan"]["advisory"] is None


def test_repair_path_never_hides_ambiguity():
    out = text_to_sign("mujhe kal bank jaana hai")
    p = out["plan"]
    assert p["gate"] == "repair"
    assert p["repair"]["type"] == "disambiguate"
    assert {o["gloss"] for o in p["repair"]["options"]} == {"YESTERDAY", "TOMORROW"}
    out2 = text_to_sign("mujhe kal bank jaana hai", {p["repair"]["token_index"]: "YESTERDAY"})
    assert out2["plan"]["gate"] == "emit"
    assert out2["frame"]["gloss"][0] == "YESTERDAY"


def test_hold_path():
    assert text_to_sign("")["plan"]["gate"] == "hold"
    assert text_to_sign("...")["plan"]["gate"] == "hold"


def test_missing_sign_is_fingerspelled():
    out = text_to_sign("Where is the toilet?")
    g = sign_of(out)["gloss"][0]
    assert g["g"] == "TOILET" and g["fingerspelled"] and g["fs_fallback"] == "T-O-I-L-E-T"


def test_degraded_sign_forces_caption():
    out = text_to_sign("Do you want water?")
    cap = next(t for t in out["plan"]["targets"] if t["kind"] == "caption")
    assert cap["forced"]
    assert "WATER" in out["plan"]["gate_reason"]


def test_high_stakes_advisory_and_stricter_gate():
    out = text_to_sign("I have pain, I need medicine.")
    assert out["plan"]["advisory"]
    assert "0.85" in out["plan"]["gate_reason"]


def test_nonmanual_track():
    wh = sign_of(text_to_sign("What is your name?"))["nonmanual"]
    assert wh[0]["brow"] == "furrowed"
    yn = sign_of(text_to_sign("Do you want water?"))["nonmanual"]
    assert yn[0]["brow"] == "raised"
    neg = sign_of(text_to_sign("I don't understand"))["nonmanual"]
    assert any(k["head"] == "shake" for k in neg)


def test_frames_follow_nonmanual():
    out = text_to_sign("What is your name?", with_frames=True)
    brows = {f["face"]["brow"] for f in out["frames"]["frames"]}
    assert "furrowed" in brows


def test_latency_budget():
    text_to_sign("warm up")                   # template bank build
    t = time.perf_counter()
    for s in ["I went to the bank yesterday.", "What is your name?", "My name is Priya."]:
        text_to_sign(s)
    per = (time.perf_counter() - t) / 3 * 1000
    assert per < 500, f"{per:.0f} ms per utterance"   # section 05-D budget is 0.4-0.9 s for the resolver alone


def test_llm_output_is_validated():
    assert validate(["YESTERDAY", "ME", "BANK", "GO"], ["ME", "BANK", "GO", "YESTERDAY"])
    assert not validate(["YESTERDAY", "ME", "BANK"], ["YESTERDAY", "ME", "BANK", "GO"])     # dropped content
    assert not validate(["YESTERDAY", "ME", "CAR", "GO"], ["YESTERDAY", "ME", "BANK", "GO"])  # invented sign
    good = lambda p: '{"gloss": ["YESTERDAY", "BANK", "ME", "GO"]}'
    bad = lambda p: '{"gloss": ["DANCE"]}'
    broken = lambda p: "not json"
    assert llm_frame("I went to the bank yesterday.", {}, call=good).gloss == ["YESTERDAY", "BANK", "ME", "GO"]
    assert llm_frame("I went to the bank yesterday.", {}, call=bad) is None      # -> rules fallback
    assert llm_frame("I went to the bank yesterday.", {}, call=broken) is None


def test_api():
    c = TestClient(app)
    r = c.post("/api/text-to-sign", json={"text": "What is your name?"})
    assert r.status_code == 200 and r.json()["plan"]["gate"] == "emit"
    assert c.get("/api/sign/BANK").status_code == 200
    assert c.get("/api/sign/NOPE").status_code == 404
    assert c.get("/").status_code == 200
    assert c.post("/api/text-to-sign", json={"text": "x" * 501}).status_code == 413
