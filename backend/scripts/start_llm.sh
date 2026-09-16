#!/usr/bin/env bash
# Phase 3: start llama-server with Qwen3 4B (Q5 by default, Q4 for CONVERSE).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
QUANT="${1:-q5}"
[ -f "$ROOT/.env" ] && set -a && . "$ROOT/.env" && set +a
MODEL="${SETU_LLM_MODEL_Q5:-data/models/qwen3-4b-instruct-q5_k_m.gguf}"
[ "$QUANT" = "q4" ] && MODEL="${SETU_LLM_MODEL_Q4:-data/models/qwen3-4b-instruct-q4_k_m.gguf}"
exec "$ROOT/third_party/llama.cpp/build/bin/llama-server" -m "$ROOT/$MODEL" \
  --host 127.0.0.1 --port 8081 -c 8192 -ngl 99 --cache-reuse 256 --jinja
