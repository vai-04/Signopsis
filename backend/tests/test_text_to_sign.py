"""Text -> sign service (pipelines C/D) and its REST routes."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from setu.config import Settings
from setu.generate.text_to_sign import TextToSign, safe_run
from setu.perceive.fake import fake_percept
from setu.resolve.gloss_llm import reorder, validate
from setu.resolve.isl_rules import text_to_frame
from setu.schemas import RenderPlan, SemanticFrame


@pytest.fixture(scope="module")
def engine():
    e = TextToSign(Settings())
    e.warmup()
    return e


def sign_of(res):
    return res.sign


def test_contracts_validate(engine):
    out = engine.run("I went to the bank yesterday.", with_frames=True).to_json()
    RenderPlan.model_validate(out["plan"])
    SemanticFrame.model_validate(out["frame"])
    json.dumps(out)
    assert out["frames"]["frames"]


def test_emit_path(engine):
    r = engine.run("I went to the bank yesterday.")
    assert r.plan.gate == "emit"
    assert r.sign.back_translation.startswith("yesterday · I · bank · go")
    assert r.plan.back_translation == r.sign.back_translation
    assert r.plan.advisory is None
    assert [t.kind for t in r.plan.targets] == ["caption", "sign"]
    assert {"sign.resolve", "sign.plan_roundtrip", "sign.total"} <= set(r.plan.timings_ms)


def test_repair_path_never_hides_ambiguity(engine):
    r = engine.run("mujhe kal bank jaana hai")
    assert r.plan.gate == "repair"
    rep = r.plan.repair
    assert rep.type == "disambiguate"
    assert {o.gloss_or_word for o in rep.options} == {"YESTERDAY", "TOMORROW"}
    assert all(o.clip.startswith("/api/sign/") for o in rep.options)
    r2 = engine.run("mujhe kal bank jaana hai", resolutions={rep.token_index: "YESTERDAY"})
    assert r2.plan.gate == "emit"
    assert r2.frame.gloss[0] == "YESTERDAY"


@pytest.mark.parametrize("text", ["", "   ", "...", "?!"])
def test_hold_path(engine, text):
    r = engine.run(text)
    assert r.plan.gate == "hold"
    assert r.plan.repair.type == "hold" and r.plan.repair.reason
    assert r.sign is None


def test_unsupported_sign_language_holds(engine):
    r = engine.run("hello", sign_lang="asl")
    assert r.plan.gate == "hold" and "ASL" in r.plan.repair.reason


def test_failure_becomes_hold(engine, monkeypatch):
    monkeypatch.setattr(engine, "_run", lambda *a, **k: 1 / 0)
    r = safe_run(engine, "hello")
    assert r.plan.gate == "hold" and r.frame.utterance == "hello"


def test_missing_sign_is_fingerspelled(engine):
    g = engine.run("Where is the toilet?").sign.gloss[0]
    assert g.g == "TOILET" and g.fingerspelled and g.fs_fallback == "T-O-I-L-E-T"
    assert g.dur_ms == 6 * 280 + 5 * 60


def test_degraded_sign_forces_caption(engine):
    r = engine.run("Do you want water?")
    assert r.plan.targets[0].forced
    assert "WATER" in r.plan.gate_reason


def test_high_stakes_advisory_and_stricter_gate(engine):
    r = engine.run("I have pain, I need medicine.")
    assert r.plan.advisory and r.frame.high_stakes
    assert "0.85" in r.plan.gate_reason
    # the backend's own medical/legal detector also counts
    assert engine.run("I have an allergy").frame.high_stakes


def test_ask_when_unsure_profile_changes_threshold(engine):
    assert "emit ≥ 0.85" in engine.run("I went home", profile="cautious").plan.gate_reason
    assert "emit ≥ 0.65" in engine.run("I went home", profile="fluent").plan.gate_reason


def test_nonmanual_track(engine):
    wh = engine.run("What is your name?").sign.nonmanual
    assert wh[0].brow == "furrowed"
    yn = engine.run("Do you want water?").sign.nonmanual
    assert yn[0].brow == "raised"
    neg = engine.run("I don't understand").sign.nonmanual
    assert any(k.head == "shake" for k in neg)


def test_frames_follow_nonmanual(engine):
    r = engine.run("What is your name?", with_frames=True)
    assert "furrowed" in {f["face"]["brow"] for f in r.frames["frames"]}
    assert r.frames["total_ms"] == r.sign.total_ms


def test_speech_source_keeps_grounding_and_speaker(engine):
    pe = fake_percept(0, t0=500)
    r = engine.run(" ".join(pe.top1()), source=pe, speaker_id="spk_1", speaker_label="Speaker 2")
    assert r.plan.gate == "emit"
    assert all(g.percept_ids == [pe.id] for g in r.frame.grounding)
    assert r.frame.speaker_id == "spk_1" and r.plan.targets[0].speaker_label == "Speaker 2"
    assert [g.g for g in r.sign.gloss[:2]] == ["GOOD", "MORNING"]


def test_latency_budget(engine):
    t = time.perf_counter()
    for s in ["I went to the bank yesterday!", "What is her name?", "My name is Priya."]:
        engine.run(s, with_frames=True)
    per = (time.perf_counter() - t) / 3 * 1000
    assert per < 500, f"{per:.0f} ms per utterance"   # Section 7: text -> sign 1-2 s end to end
    t = time.perf_counter()
    engine.run("What is her name?", with_frames=True)
    assert (time.perf_counter() - t) * 1000 < 50       # repeated phrase: served from cache


def test_llm_output_is_validated():
    assert validate(["YESTERDAY", "ME", "BANK", "GO"], ["ME", "BANK", "GO", "YESTERDAY"])
    assert not validate(["YESTERDAY", "ME", "BANK"], ["YESTERDAY", "ME", "BANK", "GO"])     # dropped content
    assert not validate(["YESTERDAY", "ME", "CAR", "GO"], ["YESTERDAY", "ME", "BANK", "GO"])  # invented sign
    frame, _ = text_to_frame("I went to the bank yesterday.")
    good = lambda s, u: '{"gloss": ["YESTERDAY", "BANK", "ME", "GO"]}'
    bad = lambda s, u: '{"gloss": ["DANCE"]}'
    broken = lambda s, u: "not json"
    better = reorder(frame, good)
    assert better.gloss == ["YESTERDAY", "BANK", "ME", "GO"] and better.provenance["path"] == "llm"
    spans = {better.gloss[g.gloss_index]: g.span for g in better.grounding}
    assert frame.utterance[slice(*spans["BANK"])] == "bank"
    assert reorder(frame, bad) is None and reorder(frame, broken) is None      # -> rules frame
    amb, _ = text_to_frame("mujhe kal bank jaana hai")
    assert reorder(amb, good) is None                                          # ambiguity goes to the human


def test_llm_path_is_used_only_when_unclear():
    calls = []

    def fake_llm(system, user):
        calls.append(user)
        return '{"gloss": ["YOUR", "NAME", "WHAT"]}'

    e = TextToSign(Settings(), llm_call=fake_llm)
    e.run("I went home")                       # short statement: rules fast path
    assert calls == []
    r = e.run("What is your name?")            # question: LLM consulted, output validated
    assert len(calls) == 1 and "sign.llm" in r.plan.timings_ms


def test_api(fake_env):
    from setu.serve.main import create_app

    with TestClient(create_app(Settings())) as c:
        assert c.get("/health").json()["sign_ready"] is True
        r = c.post("/api/text-to-sign", json={"text": "What is your name?"})
        assert r.status_code == 200
        body = r.json()
        assert body["plan"]["gate"] == "emit" and body["frames"]["frames"] and body["readback"]
        assert c.post("/api/text-to-sign", json={"text": "hi", "frames": False}).json()["frames"] is None
        assert c.post("/api/text-to-sign", json={"text": ""}).json()["plan"]["gate"] == "hold"
        assert c.post("/api/text-to-sign", json={"text": "x" * 501}).status_code == 413
        assert c.post("/api/text-to-sign", json={"text": "hi", "sign_lang": "bsl"}).status_code == 422
        assert c.post("/api/text-to-sign", json={}).status_code == 422
        assert c.get("/api/sign/bank").status_code == 200
        assert c.get("/api/sign/NOPE").status_code == 404
        assert "TOILET" in c.get("/api/lexicon").json()["vocab_without_sign"]
        assert c.get("/dev/compose").status_code == 200
        assert "sign.total" in c.get("/diag/latency").json()["stages"]
