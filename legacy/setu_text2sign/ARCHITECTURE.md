# SETU: Pipeline D (Text → Sign) architecture and execution

This repo implements **pipeline D** from the SETU v1 design with a **2D pixel
avatar** standing in for SMPL-X. It uses the three data contracts from the design
unchanged, so the other pipelines and the UI can be connected later without
rework.

```
 text (en / hi / hinglish)
   │
   ▼
┌──────────────────────────── L3 · resolve/ ─────────────────────────────┐
│ tokenize → per-token language ID → phrase + word lookup (EN/HI/Deva)   │
│ → tense-based disambiguation → drop function words → ISL reorder       │
│ → question/negation/affect → SemanticFrame (grounding + unresolved)    │
│ optional: SETU_RESOLVER=ollama (Qwen3), output validated, falls back   │
└────────────────────────────────────────────────────────────────────────┘
   │ SemanticFrame
   ▼
┌──────────────────────────── L4 · pipeline.plan_sign ───────────────────┐
│ gloss → GlossItem(dur, fs_fallback)  ·  no sign in lexicon → spell it  │
└────────────────────────────────────────────────────────────────────────┘
   │ SignTarget
   ▼
┌──────────────────────────── §07 · generate/roundtrip.py ───────────────┐
│ avatar2d.render_offline → 21-pt landmarks/hand (MediaPipe layout)      │
│ → + simulated perception noise, ×3 trials, ±60 ms segmentation slop    │
│ → Recognizer (DTW template, lattice out) → p(intended) per gloss       │
│ p < 0.70 (0.85 high-stakes) → fingerspell that gloss, force caption    │
│ → re-read → roundtrip_score, back-translation from the READ-BACK       │
└────────────────────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────── L2/L5 · the gate ──────────────────────────┐
│ nothing signable ............................... HOLD                  │
│ unresolved slot (e.g. "kal") ................... REPAIR/disambiguate   │
│ trust < 0.40 ................................... HOLD                  │
│ trust < 0.75 (0.85 high-stakes) ................ REPAIR/confirm        │
│ else ........................................... EMIT                  │
│ trust = resolver_trust × roundtrip_score                               │
└────────────────────────────────────────────────────────────────────────┘
   │ RenderPlan {gate, caption, sign(gloss + non-manual track), repair, advisory}
   ▼
 avatar2d.frames_json → pixel viewer (serve/static/index.html) or GIF (cli.py)
```

## Module map

| Path | Layer | What it does |
|---|---|---|
| `setu/schemas/__init__.py` | contracts | `PerceptEvent`, `SemanticFrame`, `RenderPlan` (Pydantic v2) |
| `setu/resolve/vocab.py` | L3 | word→gloss (EN, romanized HI, Devanagari), categories, stop words, high-stakes words |
| `setu/resolve/rules.py` | L3 | deterministic resolver: `text_to_frame(text, resolutions)` |
| `setu/resolve/grammar/isl.md` | L3 | the grammar rules, written for a Deaf consultant to review; also used as the LLM prompt |
| `setu/resolve/llm.py` | L3 | optional Qwen3 via Ollama; may only **reorder** glosses; checked against the lexicon |
| `setu/generate/hand2d.py` | L4 | parametric hand (shape, location, rotation, palm) → 21 landmarks |
| `setu/generate/signs.py` | L4 | 60+ sign lexicon + fingerspelling alphabet (**placeholder motions**) |
| `setu/generate/avatar2d.py` | L4 | timeline layout, co-articulation transitions, non-manual face track |
| `setu/generate/roundtrip.py` | §07 | recognizer + round-trip gate |
| `setu/pipeline.py` | — | `text_to_sign()`: the single entry point the UI will call |
| `setu/serve/main.py` | serve | FastAPI: `POST /api/text-to-sign`, `GET /api/sign/{gloss}`, `GET /api/lexicon` |
| `setu/serve/static/index.html` | app | pixel viewer: player, gloss strip, gate, repair card, raw JSON |
| `setu/cli.py` | test | terminal harness plus GIF export |
| `setu/eval/calibrate.py` | §12 | temperature fit, ECE, confidently-wrong rate, reliability plot |

## Contract to the UI (what "connect it later" means)

The UI only needs one call:

```http
POST /api/text-to-sign
{"text": "mujhe kal bank jaana hai", "resolutions": {}}
```

The response contains `frame` (SemanticFrame), `plan` (RenderPlan), `readback` (the
recognizer's lattice for each gloss) and `frames` (landmarks to animate).

- `plan.gate == "emit"`: play the signing and show the caption with `trust_badge`.
- `plan.gate == "repair"`, `repair.type == "disambiguate"`: show `repair.options`
  (`GET /api/sign/{gloss}` gives a preview clip for each). Resend with
  `resolutions: {repair.token_index: chosen_gloss}`.
- `plan.gate == "repair"`, `repair.type == "confirm"`: show the back-translation
  and send only after the author confirms.
- `plan.gate == "hold"`: don't sign. Show `gate_reason`.
- `plan.advisory`: show a persistent banner.
- Never auto-play anything that isn't `emit`.

## Swapping in the real components

| Now (2D harness) | Later | Interface that must not change |
|---|---|---|
| `pose_to_landmarks` | SMPL-X render → project joints to 2D | `render_offline(target) -> (times, R, L, gidx, segs)` |
| DTW `Recognizer` | ST-GCN / embedding recognizer (L1) | `classify(R, L) -> [(gloss, p)]` |
| hand-authored `LEXICON` | motion from reference ISL video | `{"dur", "R", "L"}` keyframes, or a clip lookup |
| rule resolver | Qwen3 with rules as the guard | returns a `SemanticFrame` |
| simulated noise | calibrated on recorded clips | `NOISE_SIGMA`, `TAU` |

## Execution

```bash
pip install -r requirements.txt
pytest -q                                   # 45 tests, about 4 s
python -m setu.cli "I went to the bank yesterday." --gif out.gif
uvicorn setu.serve.main:app --reload        # http://localhost:8000
python -m setu.eval.calibrate --plot        # metrics + reliability.png
python -m setu.serve.build_demo             # single-file offline demo in dist/
```

## Measured on this harness (CPU, no GPU)

- Warm latency: about 50–100 ms per utterance for resolve, plan and round-trip.
  The first call builds the template bank, about 200 ms.
- Round-trip intelligibility with low noise: 100%. Accuracy across all noise
  levels: 98.2%.
- Confidently-wrong rate among emitted reads: 0.0% at TAU = 0.08 (emit rate 82%).
  At the NLL-fitted TAU it is 0.16% (emit rate 97%).
- The planted WATER/RIVER near-duplicate is caught every time and fingerspelled.

These numbers describe the **synthetic harness**. They show that the machinery
works. They say nothing about ISL quality.

## Known limits (be explicit in any pitch)

1. The sign motions are placeholders. They have not been validated with Deaf
   signers.
2. The fingerspelling alphabet is a placeholder. Real ISL fingerspelling uses two
   hands.
3. The round-trip recognizer is a template matcher that shares its templates with
   the renderer. It catches confusable and unsigned vocabulary, but it cannot find
   errors that both the renderer and the recognizer share. The real L1 model,
   trained on human signing, closes that gap.
4. No spatial referencing, classifiers or number incorporation yet (see
   `grammar/isl.md`, items marked [REVIEW] and [TODO]).
