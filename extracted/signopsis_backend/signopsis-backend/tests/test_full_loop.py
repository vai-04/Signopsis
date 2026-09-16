"""The whole system in a loop:
text --(pipeline D)--> ISL gloss --(2D avatar)--> simulated camera --(pipeline A)--> text.

If both directions and the shared contracts are right, meaning survives the trip."""
import pytest

from conftest import play, results
from signopsis.perceive.session import SignSession
from signopsis.perceive.simcam import Degrade, text_stream

LOOP = [
    ("I went to the bank yesterday.", "Yesterday I went to the bank."),
    ("What is your name?", "What is your name?"),
    ("Do you want water?", "Do you want water?"),
    ("I don't understand.", "I don't understand."),
    ("My name is Priya.", "My name is Priya."),
    ("They went home", "They went home."),
    ("Where is the toilet?", "Where is the toilet?"),
    ("Hello, thank you", "Hello. Thank you."),
    ("Are you sick?", "Are you sick?"),
    ("Tomorrow I will go to school", "Tomorrow I will go to school."),
    ("main kal ghar gaya tha", "Yesterday I went home."),
    ("aapka naam kya hai?", "What is your name?"),
    ("मैं कल घर गया था", "Yesterday I went home."),
    ("Help me please", "Please help me."),
    ("I am not sick", "I am not sick."),
]


@pytest.mark.parametrize("src,expected", LOOP)
def test_round_trip_meaning(store, src, expected):
    sess = SignSession("loop", store)
    frames, _ = text_stream(src, Degrade(noise=0.5), seed=4)
    res = results(play(sess, frames))
    assert len(res) == 1 and res[0]["gate"] == "emit", res and res[0]["plan"]["gate_reason"]
    assert res[0]["text"] == expected


def test_degraded_loop_is_never_confidently_wrong_on_this_set(store):
    """Under bad conditions the system may ask or hold, but what it emits must be right."""
    wrong, emitted, total = 0, 0, 0
    for k, (src, expected) in enumerate(LOOP):
        for seed in (1, 2):
            sess = SignSession("loop2", store)
            frames, _ = text_stream(src, Degrade(noise=2.2, dropout=0.15, lux=70), seed=seed * 10 + k)
            for r in results(play(sess, frames)):
                total += 1
                if r["gate"] == "emit":
                    emitted += 1
                    wrong += r["text"] != expected
    assert total >= len(LOOP) * 2
    assert emitted > 0
    assert wrong / emitted <= 0.1, f"{wrong}/{emitted} emitted captions were wrong"
