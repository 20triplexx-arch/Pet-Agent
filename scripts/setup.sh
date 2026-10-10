#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
[ -f .env ] || cp .env.example .env
(cd frontend && npm ci && npm run build)
(cd backend && ../.venv/bin/python -m scripts.init_db --demo)
echo 'Ready. Run: sh scripts/start.sh'

