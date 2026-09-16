# Third-party licenses

Checked on each model card / project page when added. Only components used so far are marked ✅.

| Component | Used for | License | Status |
|---|---|---|---|
| NVIDIA Parakeet TDT 0.6B v2 (`nvidia/parakeet-tdt-0.6b-v2`) | English ASR | CC-BY-4.0 — **attribution required** (see below) | ✅ layer 1 |
| NVIDIA Streaming Sortformer 4spk v2 (`nvidia/diar_streaming_sortformer_4spk-v2`) | diarization | CC-BY-4.0 — **attribution required** (model card, checked 2026-09-16) | ✅ layer 1 |
| NVIDIA NeMo toolkit | model runtime | Apache 2.0 | ✅ layer 1 |
| Silero VAD (`silero-vad`) | voice activity | MIT | ✅ layer 1 |
| PyTorch | runtime | BSD-3-Clause | ✅ layer 1 |
| ONNX Runtime | runtime | MIT | ✅ layer 1 |
| FastAPI / Uvicorn / Pydantic | server, schemas | MIT / BSD-3 / MIT | ✅ layer 1 |
| NumPy | sign planner, round-trip gate | BSD-3-Clause | ✅ layer 2 |
| SETU placeholder sign lexicon + 2D avatar (own code) | text → sign | project code; motions are NOT validated ISL | ✅ layer 2 |
| faster-whisper + `Systran/faster-whisper-small` | CPU fallback ASR | MIT (model card, checked 2026-09-16) | ✅ code, model not downloaded |
| AI4Bharat IndicConformer | Hindi/Tamil ASR | check model card | Phase 3 |
| SpeechBrain VoxLingua107 ECAPA | language ID | check model card | Phase 3 |
| emotion2vec+ base | emotion | check model card | later |
| Qwen3 4B Instruct | resolver | Apache 2.0 | Phase 3 |
| llama.cpp | LLM server | MIT | Phase 3 |
| Qdrant | vector memory | Apache 2.0 | Phase 3 |
| intfloat/multilingual-e5-small | embeddings | MIT | Phase 3 |
| Kokoro 82M | TTS | Apache 2.0 | Phase 6 |
| MediaPipe | browser landmarks | Apache 2.0 | Phase 4 |
| RTMW / rtmlib | landmarks | Apache 2.0 | Phase 4 |
| OmniParser v2 icon detector | screen parsing | AGPL — project use only | Phase 8 |
| three.js / three-vrm / Kalidokit | avatar | MIT | Phase 7 |
| Atkinson Hyperlegible Next / Mono | fonts | OFL | web app |
| INCLUDE / ISL-CSLTR datasets | sign data | research terms | Phase 4 |

## Attribution

- *Parakeet TDT 0.6B v2* by NVIDIA, licensed under CC-BY-4.0 — https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2
- *Streaming Sortformer Diarizer 4spk v2* by NVIDIA, licensed under CC-BY-4.0 — https://huggingface.co/nvidia/diar_streaming_sortformer_4spk-v2

Deaf consultants will be credited by name in the app's About screen.
