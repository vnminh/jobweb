#!/usr/bin/env bash
# Start JobWeb (API + built frontend) on http://localhost:8000
cd "$(dirname "$0")/backend"
PY="${PYTHON:-$HOME/anaconda3/envs/attt-env/bin/python}"
exec "$PY" -W ignore -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8000}"
