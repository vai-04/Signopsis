# Run from WSL2 / Ubuntu. The venv lives in the Linux filesystem (fast) even
# though the source tree is on /mnt/c.
export UV_PROJECT_ENVIRONMENT ?= $(HOME)/.venvs/setu
export UV_LINK_MODE ?= copy
PY := uv run --no-sync python

SIGN_TEXT ?= What is your name?

.PHONY: sign setup setup-cpu check models llm backend backend-fake web ext test test-gpu types dev qdrant audio-fixtures stream latency

setup:            ## base + GPU speech stack + dev tools
	uv sync --extra asr

setup-cpu:        ## base + CPU fallback only
	uv sync --extra fallback

check:            ## Phase 0 acceptance: GPU visible to torch / onnxruntime / llama.cpp
	$(PY) backend/scripts/check_gpu.py

models:           ## prints sizes and asks before downloading
	$(PY) backend/scripts/download_models.py

llm:
	bash backend/scripts/start_llm.sh

backend:
	$(PY) -m uvicorn setu.serve.main:app --app-dir backend --host $${SETU_HOST:-127.0.0.1} --port $${SETU_PORT:-8000}

backend-fake:     ## no models needed: energy VAD + fake perceiver
	SETU_ASR=fake SETU_VAD=energy SETU_DIARIZER=none $(PY) -m uvicorn setu.serve.main:app --app-dir backend --host 127.0.0.1 --port 8000

stream:           ## stream a WAV at real-time speed: make stream WAV=data/clips/two_speakers.wav
	$(PY) backend/scripts/stream_wav.py $(WAV)

sign:             ## text -> sign over REST: make sign SIGN_TEXT="I went to the bank yesterday."
	curl -s -X POST http://127.0.0.1:$${SETU_PORT:-8000}/api/text-to-sign -H 'Content-Type: application/json' \
	  -d '{"text": "$(SIGN_TEXT)", "frames": false}' | $(PY) -m json.tool

latency:
	$(PY) -m setu.eval.latency_report

test:
	uv run pytest

test-gpu:
	uv run pytest -m gpu -v

types:
	$(PY) backend/scripts/export_types.py

qdrant:
	docker compose up -d qdrant

web:
	@echo "React app (S07) is built in a later layer. For now open http://127.0.0.1:8000/dev/listen or /dev/compose"

ext:
	@echo "Screen Glance extension is Phase 8."

dev: backend
