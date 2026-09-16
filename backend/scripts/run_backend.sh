#!/usr/bin/env bash
# Start the SETU backend inside WSL from Windows:
#   wsl -d Ubuntu -- bash /mnt/c/Users/shrey/Downloads/setu/backend/scripts/run_backend.sh
set -e
export PATH=$HOME/.local/bin:$PATH
source "$HOME/.venvs/setu/bin/activate"
cd "$(dirname "$0")/../.."
exec python -m uvicorn setu.serve.main:app --app-dir backend --host 127.0.0.1 --port "${SETU_PORT:-8000}"
