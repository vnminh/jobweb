#!/usr/bin/env bash
# Start JobWeb without Docker (API + built frontend) on http://localhost:8000. See README, section 3.
cd "$(dirname "$0")/backend"
if [ -z "${JOBUNICORN_DATA:-}" ] && [ ! -d ../jobunicorn/data/processed/graph ] && [ -d ../../jobunicorn/data/processed/graph ]; then
  export JOBUNICORN_DATA="$(cd ../../jobunicorn/data && pwd)"   # full jobunicorn checkout next to jobweb
fi
PY="${PYTHON:-$( [ -x "$HOME/anaconda3/envs/attt-env/bin/python" ] && echo "$HOME/anaconda3/envs/attt-env/bin/python" || echo python3 )}"
exec "$PY" -W ignore -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8000}"
