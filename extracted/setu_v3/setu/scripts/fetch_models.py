"""Download MediaPipe web assets + models so the camera page works offline.

    python scripts/fetch_models.py

Writes into setu/serve/static/vendor/ (git-ignored):
    tasks-vision/vision_bundle.mjs, tasks-vision/wasm/*
    models/hand_landmarker.task, pose_landmarker_lite.task, face_landmarker.task
The browser page falls back to the public CDN when these are missing, and the
Python camera client (setu.perceive.camera_cv) uses the same model files.
"""
from __future__ import annotations

import io
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "setu" / "serve" / "static" / "vendor"
TV_VERSION = "1.0.1"
NPM_TARBALL = f"https://registry.npmjs.org/@mediapipe/tasks-vision/-/tasks-vision-{TV_VERSION}.tgz"
MODELS = {
    "hand_landmarker.task": "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
    "pose_landmarker_lite.task": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
    "face_landmarker.task": "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
}


def get(url: str) -> bytes:
    print("  GET", url)
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


def main() -> int:
    ok = True
    tv = ROOT / "tasks-vision"
    (tv / "wasm").mkdir(parents=True, exist_ok=True)
    try:
        data = get(NPM_TARBALL)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for m in tar.getmembers():
                name = m.name.removeprefix("package/")
                if name == "vision_bundle.mjs" or (name.startswith("wasm/") and "module" not in name):
                    (tv / name).write_bytes(tar.extractfile(m).read())
        print("tasks-vision ->", tv)
    except Exception as e:
        ok = False
        print("tasks-vision download failed:", e)
    mdir = ROOT / "models"
    mdir.mkdir(parents=True, exist_ok=True)
    for name, url in MODELS.items():
        dest = mdir / name
        if dest.exists() and dest.stat().st_size > 1000:
            print("  have", dest.name)
            continue
        try:
            dest.write_bytes(get(url))
        except Exception as e:
            ok = False
            print(f"  {name} failed: {e}")
    print("done" if ok else "finished with errors (the page will fall back to the CDN)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
