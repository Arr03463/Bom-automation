#!/usr/bin/env bash
# AutoBOM — start both dev servers (Git Bash / macOS / Linux).
# Backend on :8000, frontend on :3000. Ctrl+C stops both.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Pick the backend venv python (Windows vs POSIX layout).
if [ -x "$ROOT/backend/.venv/Scripts/python.exe" ]; then
  PY="$ROOT/backend/.venv/Scripts/python.exe"
else
  PY="$ROOT/backend/.venv/bin/python"
fi

cleanup() { echo; echo "stopping..."; kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "AutoBOM backend  -> http://localhost:8000/api/health"
( cd "$ROOT/backend" && "$PY" main.py ) &

echo "AutoBOM frontend -> http://localhost:3000"
( cd "$ROOT/frontend" && npm run dev ) &

wait
