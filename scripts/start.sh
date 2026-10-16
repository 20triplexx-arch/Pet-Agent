#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
if [ ! -f frontend/dist/index.html ]; then (cd frontend && npm run build); fi
cd backend
../.venv/bin/python -m scripts.init_db
exec ../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${CHONGBAN_PORT:-8000}"

