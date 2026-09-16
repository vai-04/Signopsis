<<<<<<< HEAD
# Signopsis
=======
# SETU

Local-first accessibility interpreter (sign ⇄ text ⇄ voice ⇄ screen). Every perceiver emits
candidates with confidence; a trust gate decides **emit / repair / hold**. See `CLAUDE.md`
(one folder up) for the full spec.

SETU is not a certified interpreter. Use a qualified human interpreter for medical, legal, or
emergency situations.

## Status: layer 1 (speech → text) + layer 2 (text → sign)

Built so far:
- Contracts (`backend/setu/schemas`), session clock, JSONL tracing, live latency stats
- Trust + gate with default (uncalibrated) weights, high-stakes bump
- Fake perceiver (all three gates without models)
- Silero VAD segmenter → Parakeet TDT 0.6B v2 (partials by re-decoding the live segment,
  finals with N-best beam → word lattice) → Streaming Sortformer speaker labels
  (bound after 2 agreeing chunks) → trust → caption / repair / hold
- faster-whisper CPU fallback (`SETU_FALLBACK=cpu`)
- `/ws/session` WebSocket, `/diag/latency`, `/diag/state`, dev test page `/dev/listen`

Layer 2 — text → ISL sign (pipelines C and D):
- Rules resolver (`resolve/isl_rules.py`, grammar in `resolve/grammar/isl.md`): English, Hindi,
  Hinglish, Devanagari → ISL gloss (time first, verb last, wh-word last, NOT after verb,
  fingerspelling for names/unknown words). Ambiguity ("kal") is asked, never guessed.
- Optional Qwen3 reorder via llama-server (`SETU_SIGN_RESOLVER=llm`), validated against the
  lexicon, rules fallback, only for questions / longer sentences.
- `generate/`: gloss planner + non-manual track → 2D landmark avatar → **round-trip gate**
  (the avatar is read back by a recognizer; unclear signs are fingerspelled, caption forced on)
  → trust gate (same thresholds and "Ask me when unsure" profiles as captions) → `RenderPlan`.
- Every **emitted** speech caption is signed (`render.plan`, origin `speech`); repair-gated
  captions are signed only after the listener picks a word; held captions never.
- `compose.text` over the WebSocket, `POST /api/text-to-sign`, `GET /api/sign/{gloss}`,
  `GET /api/lexicon`, dev pages `/dev/listen` (mic → captions → avatar) and `/dev/compose`.

> The sign motions and fingerspelling alphabet are **placeholders**, not validated ISL.
> Replace them with reference data and review with Deaf signers before any real use.
> The v4 standalone text→sign demo this was ported from is kept in `legacy/setu_text2sign/`.

Not yet: LID/IndicConformer, prosody, Qdrant jargon memory, React app, VRM avatar, sign → text,
Screen Glance.

## Run (WSL2 Ubuntu)

```bash
cd /mnt/c/Users/shrey/Downloads/setu
cp .env.example .env                 # already done; SETU_MODEL_DIR points at ~/setu-models
make setup                           # uv sync --extra asr   (~4–5 GB, GPU stack)
make models                          # prints sizes, asks, downloads Parakeet + Sortformer (~2.9 GB)
make check                           # GPU visible to torch / onnxruntime
make test                            # model-free tests
make test-gpu                        # real-model tests on data/clips/*.wav
make backend                         # http://127.0.0.1:8000
```

Then either:
- open **http://127.0.0.1:8000/dev/listen** in Chrome on Windows → *Start mic*, or *Stream a WAV file*
- or `make stream WAV=data/clips/two_speakers.wav`

No models? `make backend-fake` runs the whole path with an energy VAD and scripted lattices.

Test clips (Windows voices, offline):
`powershell -ExecutionPolicy Bypass -File backend\scripts\make_test_audio.ps1`

Latency report from traces: `make latency`.

### Test speech → text → sign

- `/dev/listen`: speak or stream a WAV; each caption is followed by the avatar signing it
  (gloss chips + "Reads back as" line). Type in *Type to sign* for pipeline D in the same session.
- `/dev/compose`: text → sign preview with gate, round-trip scores and repair buttons.
- `make stream WAV=data/clips/two_speakers.wav` prints `SIGN` lines after each caption.
- `curl -X POST 127.0.0.1:8000/api/text-to-sign -H 'Content-Type: application/json' -d '{"text":"What is your name?","frames":false}'`

Sign settings (`.env`): `SETU_SIGN_OUTPUT` (on/off), `SETU_SIGN_FRAMES`, `SETU_SIGN_RESOLVER`
(rules/llm), `SETU_SIGN_LLM_TIMEOUT_S`. Per session: `session.start{sign_output, avatar_frames}`.

## Privacy

Audio is decoded in memory and dropped after recognition; nothing is written to disk
(`backend/tests/test_privacy.py`). Trace files hold timings and ids only; caption text is
added only with `SETU_STORE_TRANSCRIPTS=on`.
>>>>>>> 78e1baf (updated)
