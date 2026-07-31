#!/usr/bin/env bash
# Start DriveMutation frontend (Vite)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/frontend"
exec npm run dev -- --host 127.0.0.1 --port 5173
