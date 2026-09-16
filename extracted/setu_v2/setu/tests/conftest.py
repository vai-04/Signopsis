import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


@pytest.fixture
def store(tmp_path):
    from setu.memory.store import MemoryStore
    return MemoryStore(tmp_path)


@pytest.fixture
def session(store):
    from setu.perceive.session import SignSession
    return SignSession("tester", store)


def play(sess, frames, flush=True):
    """Feed wire frames into a session; return all events."""
    out = []
    for f in frames:
        out += sess.handle(f)
    if flush:
        out += sess.handle({"type": "flush"})
    return out


def results(events):
    return [e for e in events if e["type"] == "result"]
