"""Native camera client: OpenCV webcam -> MediaPipe (Python) -> SignSession.

Runs the whole sign -> text layer in one process, no browser or server:

    pip install opencv-python mediapipe
    python scripts/fetch_models.py            # once: downloads the .task models
    python -m signopsis.perceive.camera_cv --user me [--camera 0] [--lang en] [--left-handed] [--speak]

Keys in the preview window:  q quit · r reset · t <label> teach (type in terminal) · 1/2/3 answer a repair
The same WireFrame messages the browser sends are built here, so behaviour
is identical to the web page.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

MODEL_DIR = Path(__file__).resolve().parents[1] / "serve" / "static" / "vendor" / "models"
BLEND_KEYS = {"browInnerUp", "browOuterUpLeft", "browOuterUpRight", "browDownLeft", "browDownRight",
              "cheekPuff", "jawOpen", "mouthPucker"}


def results_to_wire(t_ms: float, w: int, h: int, hand_res, pose_res, face_res, lux: Optional[float]) -> dict:
    """Convert MediaPipe Tasks results (Python API) into a WireFrame dict."""
    hands = []
    if hand_res is not None:
        for i, lms in enumerate(hand_res.hand_landmarks or []):
            cat = (hand_res.handedness[i][0] if hand_res.handedness and i < len(hand_res.handedness) else None)
            hands.append({"lm": [[p.x, p.y, p.z] for p in lms],
                          "label": cat.category_name if cat else "",
                          "score": float(cat.score) if cat else 1.0})
    pose = None
    if pose_res is not None and pose_res.pose_landmarks:
        pose = [[p.x, p.y, p.z, float(p.visibility if p.visibility is not None else 1.0)]
                for p in pose_res.pose_landmarks[0][:25]]
    face = None
    if face_res is not None and face_res.face_landmarks:
        bs = {}
        if face_res.face_blendshapes:
            for c in face_res.face_blendshapes[0]:
                if c.category_name in BLEND_KEYS:
                    bs[c.category_name] = round(float(c.score), 3)
        nose = face_res.face_landmarks[0][1]
        face = {"bs": bs, "nose": [nose.x, nose.y]}
    return {"type": "frame", "t": round(t_ms, 1), "w": w, "h": h, "hands": hands, "pose": pose,
            "face": face, "lux": lux, "mirrored": False}


def _require(path: Path) -> str:
    if not path.exists():
        sys.exit(f"missing {path}. Run: python scripts/fetch_models.py")
    return str(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default="default")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--lang", default="en", choices=["en", "hi"])
    ap.add_argument("--left-handed", action="store_true")
    ap.add_argument("--speak", action="store_true", help="speak emitted captions (pyttsx3)")
    ap.add_argument("--no-window", action="store_true")
    a = ap.parse_args()

    import cv2
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision

    from signopsis.perceive.session import SignSession

    RM = vision.RunningMode.VIDEO
    hands = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=_require(MODEL_DIR / "hand_landmarker.task")),
        running_mode=RM, num_hands=2))
    pose = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=_require(MODEL_DIR / "pose_landmarker_lite.task")),
        running_mode=RM, num_poses=1))
    face = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=_require(MODEL_DIR / "face_landmarker.task")),
        running_mode=RM, num_faces=1, output_face_blendshapes=True))

    tts = None
    if a.speak:
        try:
            import pyttsx3
            tts = pyttsx3.init()
        except Exception:
            print("pyttsx3 not available; captions will not be spoken")

    sess = SignSession(a.user, out_lang=a.lang, dominant="left" if a.left_handed else "right")
    cap = cv2.VideoCapture(a.camera)
    if not cap.isOpened():
        sys.exit(f"cannot open camera {a.camera}")
    t0 = time.monotonic()
    n = 0
    last_face = None
    lux = None
    pending = None
    status = "ready"
    caption = ""
    print("SIGNOPSIS camera client running. q = quit, r = reset, t = teach, 1/2/3 = answer repair")
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        n += 1
        t_ms = (time.monotonic() - t0) * 1000.0
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        ts = int(t_ms)
        hr = hands.detect_for_video(img, ts)
        pr = pose.detect_for_video(img, ts)
        if n % 2 == 0:
            last_face = face.detect_for_video(img, ts)
        if n % 10 == 1:
            lux = float(cv2.cvtColor(cv2.resize(bgr, (16, 12)), cv2.COLOR_BGR2GRAY).mean())
        h, w = bgr.shape[:2]
        events = sess.handle(results_to_wire(t_ms, w, h, hr, pr, last_face, lux))
        for e in events:
            if e["type"] == "live":
                status = ("SIGNING" if e["signing"] else "idle") + (f" - {e['hint']}" if e.get("hint") else "")
            elif e["type"] == "partial":
                status = "SIGNING: " + " ".join(e["gloss"])
            elif e["type"] == "result":
                plan = e["plan"]
                caption = f"[{plan['gate']}] {e['text'] or plan['gate_reason']}"
                print(caption, "|", " ".join(f"{s['display']}:{s['trust']:.2f}" for s in e["slots"]))
                pending = plan if plan.get("repair") else None
                if pending:
                    opts = pending["repair"]["options"]
                    print("  repair:", pending["repair"]["prompt"],
                          " ".join(f"[{i + 1}] {o['label']}" for i, o in enumerate(opts)))
                if plan["gate"] == "emit" and tts:
                    tts.say(e["text"]); tts.runAndWait()
            elif e["type"] in ("teach_offer", "enroll_progress", "enrolled"):
                print(e)
        if not a.no_window:
            view = cv2.flip(bgr, 1)
            for lms in (hr.hand_landmarks or []):
                for p in lms:
                    cv2.circle(view, (int((1 - p.x) * w), int(p.y * h)), 3, (80, 200, 255), -1)
            cv2.putText(view, status[:60], (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(view, caption[:60], (10, h - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (80, 255, 120), 2)
            cv2.imshow("SIGNOPSIS sign -> text", view)
            k = cv2.waitKey(1) & 0xFF
            if k == ord("q"):
                break
            if k == ord("r"):
                sess.handle({"type": "reset"})
            if k == ord("t"):
                label = input("teach label: ").strip()
                if label:
                    print(sess.handle({"type": "enroll_start", "label": label}))
            if k in (ord("1"), ord("2"), ord("3")) and pending:
                opts = pending["repair"]["options"]
                i = k - ord("1")
                if i < len(opts):
                    for e in sess.handle({"type": "repair_choice", "frame_id": pending["frame_id"],
                                          "slot": pending["repair"]["slot"], "choice": opts[i]["gloss"]}):
                        if e["type"] == "result":
                            caption = f"[{e['gate']}] {e['text']}"
                            print("  ->", caption)
                    pending = None
    cap.release()
    if not a.no_window:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
