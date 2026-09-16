#!/usr/bin/env bash
# Phase 3: build llama.cpp with CUDA (needs cmake + CUDA toolkit 12.8+ in WSL).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DIR="$ROOT/third_party/llama.cpp"
command -v cmake >/dev/null || { echo "cmake missing: sudo apt install cmake build-essential"; exit 1; }
command -v nvcc >/dev/null || { echo "nvcc missing: install cuda-toolkit-12-8 (or newer) from NVIDIA's WSL-Ubuntu repo"; exit 1; }
[ -d "$DIR" ] || git clone --depth 1 https://github.com/ggml-org/llama.cpp "$DIR"
cmake -S "$DIR" -B "$DIR/build" -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=120 -DLLAMA_CURL=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build "$DIR/build" -j --target llama-server
"$DIR/build/bin/llama-server" --version
