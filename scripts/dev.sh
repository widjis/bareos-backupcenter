#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python || ! -d node_modules ]]; then
  echo "Install dependencies first. See docs/LOCAL-DEVELOPMENT.md."
  exit 1
fi
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8001 &
backend_pid=$!
cleanup() { kill "$backend_pid" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
npm run dev
