"""The live sign->text layer end to end (simulated camera -> SignSession)."""
import time

import pytest

from conftest import play, results
from setu.perceive.session import SignSession, normalise_label
from setu.perceive.simcam import Degrade, plan_for, stream, text_stream
from setu.schemas import PerceptEvent, RenderPlan, SemanticFrame


def run_text(sess, text, deg=None, seed=3, t0=0.0):
    frames, info = text_stream(text, deg or Degrade(noise=0.4), seed=seed, t0=t0)
    return results(play(sess, frames)), info


def run_gloss(sess, gloss, deg=None, seed=0, t0=0.0):
    return results(play(sess, stream(plan_for(gloss), deg or Degrade(noise=0.4), seed=seed, t0=t0)))


@pytest.mark.parametrize("text,expected", [
    ("I went to the bank yesterday.", "Yesterday I went to the bank."),
    ("What is your name?", "What is your name?"),
    ("Do you want water?", "Do you want water?"),
    ("I don't understand.", "I don't understand."),
    ("My name is Priya.", "My name is Priya."),
    ("Where is the toilet?", "Where is the toilet?"),
    ("Are you sick?", "Are you sick?"),
    ("Tomorrow I will go to school", "Tomorrow I will go to school."),
])
def test_clean_signing_is_emitted_correctly(session, text, expected):
    res, _ = run_text(session, text)
    assert len(res) == 1
    r = res[0]
    assert r["gate"] == "emit", r["plan"]["gate_reason"]
    assert r["text"] == expected
    # the three contracts validate
    PerceptEvent.model_validate(r["percept"])
    SemanticFrame.model_validate(r["frame"])
    plan = RenderPlan.model_validate(r["plan"])
    assert any(t.kind == "tts" for t in plan.targets)          # sign -> voice target present on emit
    # grounding: every non-space character of the caption traces back to evidence
    covered = set()
    for g in r["frame"]["grounding"]:
        covered |= set(range(*g["span"]))
        assert g["percept_ids"] == [r["percept"]["id"]]
    assert all(i in covered for i, ch in enumerate(r["text"]) if ch.isalpha())


def test_high_stakes_banner(session):
    res, _ = run_text(session, "I have pain, I need medicine.")
    assert res[0]["plan"]["advisory"]
    assert "0.85" in res[0]["plan"]["gate_reason"] or res[0]["gate"] != "emit"


def test_darkness_is_held_with_a_reason(session):
    res, _ = run_text(session, "I went to the bank yesterday.", Degrade(noise=3.5, dropout=0.5, lux=12), seed=5)
    assert res and all(r["gate"] in ("hold", "repair") for r in res)
    held = [r for r in res if r["gate"] == "hold"]
    if held:
        assert held[0]["text"] == ""
        assert "dark" in held[0]["plan"]["gate_reason"].lower() or held[0]["plan"]["repair"]


def test_never_speaks_unless_emitted(session):
    res, _ = run_text(session, "I went to the bank yesterday.", Degrade(noise=4, dropout=0.5, lux=15), seed=9)
    for r in res:
        has_tts = any(t["kind"] == "tts" for t in r["plan"]["targets"])
        assert has_tts == (r["gate"] == "emit")


def test_disambiguation_repair_and_memory(session):
    r = run_gloss(session, ["ME", "RIVER", "GO"])[0]
    assert r["gate"] == "repair" and r["plan"]["repair"]["type"] == "disambiguate"
    opts = [o["gloss"] for o in r["plan"]["repair"]["options"]]
    assert {"RIVER", "WATER"} <= set(opts)
    assert all(o["clip"] for o in r["plan"]["repair"]["options"] if o["gloss"] in ("RIVER", "WATER"))
    fixed = session.handle({"type": "repair_choice", "frame_id": r["plan"]["frame_id"],
                            "slot": r["plan"]["repair"]["slot"], "choice": "RIVER"})[0]
    assert fixed["gate"] == "emit" and fixed["text"] == "I go to the river."
    assert fixed["slots"][1]["source"] == "user" and fixed["slots"][1]["trust"] == 1.0
    # the same ambiguity in the same context is not asked twice
    again = run_gloss(session, ["ME", "RIVER", "GO"], seed=1, t0=20000)[0]
    assert again["gate"] == "emit" and again["slots"][1]["gloss"] == "RIVER" and again["slots"][1]["source"] == "user"


def test_context_resolves_without_asking(session):
    r = run_gloss(session, ["YOU", "WATER", "WANT"], seed=2)[0]
    assert r["gate"] == "emit" and r["slots"][1]["gloss"] == "WATER"


def test_neither_dismisses(session):
    r = run_gloss(session, ["ME", "RIVER", "GO"])[0]
    out = session.handle({"type": "repair_choice", "frame_id": r["plan"]["frame_id"], "slot": 1, "choice": "__none__"})
    assert out[0]["type"] == "repair_done"
    assert session.handle({"type": "repair_choice", "frame_id": r["plan"]["frame_id"], "slot": 1, "choice": "RIVER"})[0]["type"] == "error"


def test_unknown_sign_teach_and_recognise(session, store):
    r1 = run_gloss(session, ["MY", "NAME", "DEMO-NAMESIGN"], seed=0)[0]
    assert r1["gate"] == "hold" and r1["slots"][-1]["kind"] == "unknown"
    ev = play(session, stream(plan_for(["DEMO-NAMESIGN", "COME"]), Degrade(noise=0.4), seed=1, t0=10000))
    assert any(e["type"] == "teach_offer" for e in ev)
    prog = session.handle({"type": "enroll_from_unknown", "label": "Kushagra"})[0]
    assert prog["have"] == 2 and prog["label"] == "FS:KUSHAGRA"
    for k in range(2):
        ev = play(session, stream(plan_for(["DEMO-NAMESIGN"]), Degrade(noise=0.4), seed=10 + k, t0=20000 + k * 5000))
    done = [e for e in ev if e["type"] == "enrolled"][0]
    assert done["warning"] is None
    assert [s["label"] for s in store.list_signs("tester")] == ["FS:KUSHAGRA"]
    r = run_gloss(session, ["MY", "NAME", "DEMO-NAMESIGN"], seed=20, t0=40000)[0]
    assert r["gate"] == "emit" and r["text"] == "My name is Kushagra."
    # persisted: a new session for the same user knows the sign, another user does not
    fresh = SignSession("tester", store)
    assert run_gloss(fresh, ["DEMO-NAMESIGN", "COME", "FINISH"], seed=21)[0]["text"] == "Kushagra came."
    other = SignSession("someone-else", store)
    assert run_gloss(other, ["MY", "NAME", "DEMO-NAMESIGN"], seed=22)[0]["gate"] == "hold"
    # forget
    out = session.handle({"type": "forget_sign", "label": "Kushagra"})[0]
    assert out["removed"] == 5 and out["signs"] == []


def test_explicit_teaching_four_shots(session):
    assert session.handle({"type": "enroll_start", "label": "office"})[0]["label"] == "FS:OFFICE"
    ev = []
    for k in range(4):
        ev += play(session, stream(plan_for(["DEMO-JARGON"]), Degrade(noise=0.4), seed=30 + k, t0=k * 5000))
    assert [e["have"] for e in ev if e["type"] == "enroll_progress"] == [1, 2, 3]
    assert any(e["type"] == "enrolled" for e in ev)
    r = run_gloss(session, ["ME", "DEMO-JARGON", "GO"], seed=40, t0=50000)[0]
    assert r["gate"] == "emit" and r["text"] == "I go to Office."


def test_enroll_cancel_and_bad_label(session):
    assert session.handle({"type": "enroll_start", "label": "  "})[0]["type"] == "error"
    session.handle({"type": "enroll_start", "label": "x"})
    assert session.handle({"type": "enroll_cancel"})[0]["cancelled"]
    assert session.enroll is None


def test_left_handed_and_mirrored_signer(store):
    sess = SignSession("lefty", store, dominant="left")
    res, _ = run_text(sess, "What is your name?", Degrade(noise=0.4, lefty=True, mirrored=True))
    assert res[0]["gate"] == "emit" and res[0]["text"] == "What is your name?"


def test_hindi_output(store):
    sess = SignSession("hi", store, out_lang="hi")
    res, _ = run_text(sess, "I went to the bank yesterday.")
    assert res[0]["text"] == "कल मैं बैंक गया।" and res[0]["frame"]["lang"] == "hi"


def test_live_and_partial_events(session):
    frames, _ = text_stream("I have pain, I need medicine.", Degrade(noise=0.4), seed=1)
    ev = play(session, frames)
    kinds = [e["type"] for e in ev]
    assert "phrase_start" in kinds and "live" in kinds and "partial" in kinds
    assert kinds.index("phrase_start") < kinds.index("result")
    live = next(e for e in ev if e["type"] == "live" and e["signing"])
    assert live["hands"]["R"] and live["anchor"]


def test_bad_messages_are_errors(session):
    assert session.handle({"type": "nope"})[0]["type"] == "error"
    assert session.handle({"type": "repair_choice", "slot": 0, "choice": "X"})[0]["type"] == "error"
    assert normalise_label("bank") == "BANK" and normalise_label("Priya") == "FS:PRIYA"


def test_phrase_latency(session):
    frames, _ = text_stream("I went to the bank yesterday.", Degrade(noise=0.4), seed=3)
    for f in frames[:-25]:
        session.handle(f)
    t = time.perf_counter()
    for f in frames[-25:]:
        session.handle(f)
    session.handle({"type": "flush"})
    assert (time.perf_counter() - t) * 1000 < 1500     # design budget: first caption 0.5-1 s after phrase end


def test_teaching_rejects_multi_sign_samples(session):
    session.handle({"type": "enroll_start", "label": "bad"})
    ev = play(session, stream(plan_for(["MY", "NAME", "HELLO"]), Degrade(noise=0.4), seed=0))
    prog = [e for e in ev if e["type"] == "enroll_progress"][-1]
    assert prog["have"] == 0 and "more than one sign" in prog["warning"]
