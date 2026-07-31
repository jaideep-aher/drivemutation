#!/usr/bin/env bash
# Start DriveMutation backend (Stage 1)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
