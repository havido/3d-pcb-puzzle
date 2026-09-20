#!/usr/bin/env bash
# Run the API and the UI together: ./web/dev.sh  (Ctrl-C stops both)
set -euo pipefail
cd "$(dirname "$0")/.."

[ -d .venv ] || { echo "no .venv — run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pip install -e ."; exit 1; }
[ -d web/app/node_modules ] || (cd web/app && npm install)

.venv/bin/uvicorn api.main:app --app-dir web --reload --port 8765 &
API=$!
trap 'kill $API 2>/dev/null || true' EXIT
(cd web/app && npm run dev)
