"""3D avatar (three.js) checks, run headlessly in Node: rig math, retargeting and a full plan playback."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from setu.pipeline import text_to_sign

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def _run(*args):
    r = subprocess.run([NODE, *args], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def test_rig_math_and_retarget():
    out = _run("tests/js/rig.test.mjs")
    assert "rig tests passed" in out


@pytest.mark.parametrize("text", ["Hello, my name is Priya. What is your name?", "I don't understand.",
                                  "Where is the toilet?"])
def test_avatar_plays_a_real_plan(tmp_path, text):
    plan = text_to_sign(text, with_frames=True)
    f = plan["frames"]["frames"][0]
    assert set(f["Rq"]) == {"c", "s", "x", "y", "r", "p"}          # contract for the 3D avatar
    p = tmp_path / "plan.json"
    p.write_text(json.dumps(plan))
    assert "avatar ok" in _run("tests/js/avatar.test.mjs", str(p))


def test_avatar_page_is_served():
    from fastapi.testclient import TestClient
    from setu.serve.main import app
    c = TestClient(app)
    assert c.get("/avatar").status_code == 200
    for path in ("/static/avatar3d/avatar.js", "/static/avatar3d/rig.js", "/static/lib/three-bundle.min.js"):
        assert c.get(path).status_code == 200, path
