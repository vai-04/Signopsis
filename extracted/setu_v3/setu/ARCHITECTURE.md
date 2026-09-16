# SETU architecture and execution (v0.2)

This build has both directions of the interpreter working end to end on a CPU laptop:

| Direction | Pipeline | Status |
|---|---|---|
| **Sign → text (and voice)** | A + B | **Live**: camera → MediaPipe in the browser → WebSocket → recognizer → trust → resolver → caption / speech, with repair and 4-shot teaching |
| **Text → sign** | D | Rules resolver → 2D avatar → round-trip gate → pixel viewer |
| Voice → sign | C | Not built. Planned slot: `LISTEN` mode, shares the pipeline D back end |
| Screen → speech | E | Not built. Planned slot: `SCREEN` mode |

Both directions use the same three contracts (`PerceptEvent`, `SemanticFrame`,
`RenderPlan`), the same signing space, and **the same sign recognizer**. The
recognizer that reads your camera also checks the avatar before it plays
(design §07).

---

## 1. Sign → text: the live layer

```
 BROWSER (raw video never leaves the page)                         SERVER  (/ws/sign)
 ┌──────────────────────────────────────────┐   WireFrame JSON     ┌─────────────────────────────────────────────────────────────┐
 │ getUserMedia 640x480@30                  │  ~30 msg/s, ~6 KB    │ L0  landmarks.Normalizer                                    │
 │ MediaPipe tasks-vision (WASM/GPU)        │ ───────────────────▶ │     image coords → body-centred signing space (shoulders),  │
 │   HandLandmarker x2, PoseLandmarker lite │                      │     handedness = pose wrists + continuity + label           │
 │   FaceLandmarker + blendshapes (every 2) │                      │ L1  segment.PhraseTracker   hands up … hands down           │
 │ 16x12 luma probe → "lux"                 │                      │     segment.decode_phrase   level-building DP over spans     │
 │ or: Simulated source (/api/simcam)       │                      │       recognizer.Index      DTW prototypes (base + user),   │
 └──────────────────────────────────────────┘                      │                             shortlist → exact DTW            │
          ▲                                                          │       ±2-frame re-reads → disagreement; unknown detection   │
          │  live · partial · result · repair ·                      │     nonmanual.analyse  brows → question type, head shake →  │
          │  teach_offer · enroll_progress · enrolled                │                        negation, speed vs baseline → prosody│
          └──────────────────────────────────────────────────────────│ L2  fuse.trust  quality σ(·) → trust σ(margin, quality,     │
                                                                     │                 disagreement, novelty, fs) (fitted)         │
                                                                     │     coverage = signing time explained by recognized signs   │
                                                                     │ L3  sign_to_text.decode_context  Viterbi: vision + ISL order │
                                                                     │       + co-occurrence + history + this user's jargon        │
                                                                     │     sign_to_text.realize  ISL → English / Hindi, grounded   │
                                                                     │ L2  gate: emit / repair (disambiguate | resign) / hold      │
                                                                     │ L4  RenderPlan: caption (+trust badge) · TTS target · repair │
                                                                     │ L5  repair → lock slot → jargon memory; teach → prototypes  │
                                                                     │ mem memory.MemoryStore  per-user prototypes + jargon (files; │
                                                                     │                          optional Qdrant mirror)            │
                                                                     └─────────────────────────────────────────────────────────────┘
```

### How the gate decides (in order)

1. **Unknown sign** in the phrase → HOLD.
   - If the view is bad (dark, no body, hands lost, overlapping or blurry), it gives that reason instead.
   - Otherwise it offers *Teach me this sign*. If the same unknown sign comes up twice, the system offers teaching on its own.
2. **Coverage < 0.40** (most of the signing wasn't understood) → HOLD, with the reason.
3. **Lowest slot trust < 0.40** → HOLD, with a specific reason (too dark, step back, hands lost, overlap, blur).
4. **Coverage < 0.65** → REPAIR: "Did I get all of that?"
5. **Lowest slot trust < 0.75** → REPAIR.
   - If there is a close competitor, it asks **"Which sign did you mean?"** and shows avatar previews of both options.
   - Otherwise it asks the signer to sign again.
   - A slot that is still ambiguous after context has its trust capped at 0.40 + its context margin, so it can never pass as certain.
6. Otherwise → **EMIT**: caption plus a TTS target.
   - Medical or legal signs raise both thresholds by 0.10 and show the interpreter banner.

**Speech:** a phrase is spoken only when EMIT. **Prosody:** affect stays neutral until the signer's own speed baseline is known.

### Teaching (design §09)

- **Starting:** either `enroll_start {label}`, or accept the teach offer after an unknown sign.
- **Samples:** 4 samples; each phrase is one sample.
  - The hands rising and falling are trimmed off.
  - A sample that the recognizer reads as several known signs is rejected.
- **Storage:** the samples plus their mean are stored per user, and the recognizer index is rebuilt at once. No retraining.
- **Tie-breaking:** the user's prototypes get a 15% distance discount, so "my" signs win ties.
- **Labels:** a known word maps to its gloss ("bank" → `BANK`). Anything else becomes a proper noun (`FS:KUSHAGRA` → "Kushagra").

---

## 2. Text → sign (pipeline D)

It is unchanged from v0.1, with one integration change: `generate/roundtrip.py` now reads the rendered avatar
with the **live recognizer** (`perceive.recognizer.Index`). One model serves both directions.

---

## 2b. The 3D signer (`/avatar`, three.js)

```
RenderPlan frames (30 fps)                 static/avatar3d/rig.js (pure math, also runs in Node)
  frame.Rq / frame.Lq  ───────────────▶  signingToWorld(x,y)  → wrist target (depth depends on where
  {c:[5 curls], s, x, y, r, p}             │                     the hand is: face, chest, side, rest)
  frame.face {brow, head, mouth, hx, hy}   ├ solveArm()          two-bone IK, elbow drops and flares out
                                           ├ handQuaternion()    anatomical wrist basis (thumb to the midline
                                           │                     when the palm faces the viewer)
                                           └ HandRig.setShape()  15 finger joints, MediaPipe joint order
                                                  │
static/avatar3d/avatar.js  ◀──────────────────────┘  procedural cartoon: lathe head, 400 instanced curls,
                                                     happy/open eyes with blinks, brows, mouth, hoodie, jeans
static/avatar3d/app.js     60 fps loop: interpolates the 30 fps frames, orbit camera, views, styling,
                           mirror-me, pose lab
```

- **Same data as the 2D avatar.** `avatar2d.frames_json` now also emits `Rq`/`Lq` hand parameters per frame. The 3D and 2D avatars therefore render the **same plan**, and the round-trip gate (2D landmarks) still guards what is played.
- **Mirror me.** Webcam → MediaPipe (browser) → `retargetFrame()` → the same parameters → avatar.
  - The inverse mapping is self-calibrated against the rig, so the two directions are consistent.
  - `tests/js/rig.test.mjs` poses the rig, projects it to fake MediaPipe landmarks and checks that retargeting recovers the pose: wrist within 1.5 units, curls within 0.2, palm direction and rotation.
- **Facial grammar.** The face follows the plan: brows (raised/furrowed), head tilt, shake and nod, and mouth. Eyes are "happy" (closed, smiling) when idle and open while signing.
- **No model files** are needed. `static/lib/three-bundle.min.js` is three.js r186 + OrbitControls (MIT), bundled locally so the page also works offline.
- **To swap in a rigged GLB later**, keep `solveFrame()` and apply `S/E/W` and `quat` to the model's upper-arm, forearm and hand bones, and the finger curls to its finger bones.

## 3. Contracts: the integration surface

### WebSocket `/ws/sign?user=<id>&lang=en|hi&dominant=right|left`

| Client → server | Meaning |
|---|---|
| `{"type":"frame", t, w, h, hands:[{lm:[[x,y,z]×21], label, score}], pose:[[x,y,z,vis]×25]\|null, face:{bs:{…}, nose:[x,y]}\|null, lux, mirrored}` | One video frame (schema `WireFrame`). Coordinates are image-normalized and unmirrored, unless `mirrored:true` |
| `{"type":"batch", items:[…]}` | Several messages in order |
| `{"type":"repair_choice", frame_id, slot, choice}` | `choice` is a gloss, `__none__`, `__accept__` or `__teach__` |
| `{"type":"enroll_start", label}` / `enroll_from_unknown` / `enroll_cancel` | Teaching |
| `{"type":"forget_sign", label}` / `list_signs` | Memory |
| `{"type":"config", out_lang, dominant}` / `reset` / `flush` | Session |

| Server → client | Meaning |
|---|---|
| `hello` | User, taught signs, vocabulary |
| `live` | Every 3 frames: signing?, hands R/L, body anchor, lux, brows, hint |
| `phrase_start`, `partial {gloss}` | While signing |
| `result {text, gate, slots[], percept, frame, plan}` | `percept` = PerceptEvent, `frame` = SemanticFrame, `plan` = RenderPlan |
| `teach_offer`, `enroll_progress`, `enrolled`, `signs`, `repair_done`, `error` | |

Every `result.frame.grounding[]` maps a character span of the caption to the percept id and its time range. Function words take the grounding of the word next to them.

### HTTP

| Endpoint | Purpose |
|---|---|
| `POST /api/text-to-sign` | Pipeline D |
| `GET /api/sign/{gloss}` | Avatar clip (used by repair previews) |
| `GET /api/simcam?text=… \| gloss=A,B&severity=0..1&lefty&mirrored&seed&t0` | Simulated camera |
| `GET/DELETE /api/users/{u}/signs[/{label}]` | Taught signs |
| `GET/POST /api/mode` | Mode manager (WATCH / SPEAK / CONVERSE / LISTEN / SCREEN) with the design's VRAM plan |

### Python (in-process)

```python
from setu.perceive.session import SignSession
sess = SignSession(user="me")                 # MemoryStore under ./data (SETU_DATA to move it)
for msg in wire_frames: events = sess.handle(msg)
```

The OpenCV client (`setu/perceive/camera_cv.py`), the tests and the WebSocket all use exactly this call.

---

## 4. Swapping in the heavy components later

| Now | Later (GPU build) | What stays the same |
|---|---|---|
| DTW prototype recognizer | ST-GCN / embedding encoder + Qdrant | `Index.label_distances(Q) -> (S, labels)`, `Proto`, user prototypes |
| Heuristic phrase tracker + DP | Learned boundary head | `decode_phrase(P, index) -> [Seg]` |
| Rules + Viterbi resolver | Qwen3-4B, with the rules as a guard | `SlotIn` in → `Resolved` / `SemanticFrame` out |
| Browser Web Speech | Kokoro-82M | `TTSTarget {text, rate, pitch, volume, emphasis}` |
| 2D avatar | SMPL-X | `render_offline(target)` → landmarks |
| Simulated trust data | Recorded, labelled clips | `python -m setu.fuse.fit` (same code) |

---

## 5. Running it

```bash
pip install -r requirements.txt
python scripts/fetch_models.py          # once, for offline MediaPipe (otherwise the page uses the CDN)
uvicorn setu.serve.main:app             # http://localhost:8000 → Sign → text → Start camera
pytest -q                               # 155 tests, about 50 s (the 3D avatar tests need Node)
```

Without a webcam: open the page, choose **Simulated**, or run
`python -m setu.perceive.simulate "I went to the bank yesterday." --severity 0.5`.

Native (no browser): `python -m setu.perceive.camera_cv --user me`, after
`pip install opencv-python mediapipe`.

`getUserMedia` works on `http://localhost`. To use a phone or another machine, serve over HTTPS.

---

## 6. Evaluation (§12), measured on the simulator

`python -m setu.fuse.fit --n 400 --plot` → `setu/eval/sign_report.json` and `sign_reliability.png`.
See the README for the numbers from this build. The simulator mixes six severity levels, from studio conditions to
awful (landmark jitter up to about 4 units, 60% hand dropout, darkness, left-handed and mirrored signers,
body-size and position changes).

## 7. Known limits

1. **The core claim is unproven on real people.** The sign motions, the fingerspelling alphabet and the
   recognizer templates are placeholders made for the 2D avatar. **Real ISL signed at a real camera will
   mostly come out as "unknown"** until you teach those signs (4 samples each) or replace the lexicon
   with recorded ISL prototypes. The pipeline, trust, repair and teaching all work today. The base
   vocabulary does not.
2. **Trust weights come from simulated degradations.** Refit them on recorded clips before quoting any numbers.
3. **Hindi output is rough** (see `grammar/isl.md`, rule 24).
4. **The browser camera path was tested up to model loading.** A fake camera was used, and the MediaPipe JS
   and WASM loaded, but the model download was blocked in the build sandbox. On your machine the models
   come from Google's CDN or from `scripts/fetch_models.py`. Every step after the landmarks is covered by
   tests, through the same WebSocket.
5. **Not built yet:** pipelines C and E, diarization, and cloud escalation.
6. **The 3D avatar's motions are the same placeholders** as the 2D lexicon. Its arm and hand kinematics
   are anatomical, but the signs themselves still need ISL reference data and review by Deaf signers.
   *Mirror me* was tested with simulated landmarks. Real webcam retargeting accuracy has not been
   measured yet.
