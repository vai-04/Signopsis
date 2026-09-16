import time

from setu.config import Settings
from setu.fuse.gate import decide, thresholds
from setu.fuse.trust import compute_trust, slot_margin
from setu.generate.caption import plan_caption
from setu.perceive.fake import fake_percept
from setu.resolve.router import frame_from_percept
from setu.schemas import Candidate, LatticeSlot


def _gate(kind, profile="balanced", hs=False):
    ev = fake_percept(kind)
    tr = compute_trust(ev)
    return ev, tr, decide(tr.value, thresholds(Settings(), profile, hs))


def test_three_gates_from_fake_lattices():
    assert _gate(0)[2] == "emit"
    assert _gate(1)[2] == "repair"
    assert _gate(2)[2] == "hold"


def test_single_candidate_margin_assumes_hidden_rival():
    assert abs(slot_margin(LatticeSlot(slot=0, cands=[Candidate(value="a", score=0.9)])) - 0.85) < 1e-9
    two = LatticeSlot(slot=0, cands=[Candidate(value="a", score=0.5), Candidate(value="b", score=0.1)])
    assert abs(slot_margin(two) - 0.3) < 1e-9          # half of unassigned 0.4 outranks "b"


def test_high_stakes_raises_thresholds():
    base, hs = thresholds(Settings()), thresholds(Settings(), high_stakes=True)
    assert abs(hs.emit - base.emit - 0.10) < 1e-9 and abs(hs.repair - base.repair - 0.10) < 1e-9


def test_profiles_order():
    c, b, f = (thresholds(Settings(), p) for p in ("cautious", "balanced", "fluent"))
    assert c.emit > b.emit > f.emit


def test_trust_and_gate_under_15ms():
    ev = fake_percept(1)
    th = thresholds(Settings())
    n = 500
    t = time.perf_counter()
    for _ in range(n):
        decide(compute_trust(ev).value, th)
    assert (time.perf_counter() - t) / n * 1000 < 15


def test_repair_plan_marks_uncertain_span():
    ev, tr, gate = _gate(1)
    frame = frame_from_percept(ev, tr)
    plan = plan_caption(frame, ev, gate)
    cap = plan.targets[0]
    assert cap.trust_badge == "medium"
    (a, b), = cap.uncertain_spans
    assert cap.text[a:b] == "their"
    assert [o.gloss_or_word for o in plan.repair.options] == ["their", "there"]


def test_hold_plan_has_no_caption_and_specific_reason():
    ev, tr, gate = _gate(2)
    plan = plan_caption(frame_from_percept(ev, tr), ev, gate)
    assert plan.targets == []
    assert plan.repair.reason == "Too much background noise"
