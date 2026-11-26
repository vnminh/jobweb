#!/usr/bin/env bash
# Maintainers only: import CareerBuilder window 7 into a temporary PostgreSQL and dump it to docker/assets/jobweb.dump,
# which docker/db.Dockerfile bakes into the database image.
#   docker/build_db_dump.sh /path/to/jobunicorn/data        (needs the backend image built first)
set -euo pipefail
DATA="$(cd "${1:?usage: $0 <jobunicorn/data>}" && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
IMG="${BACKEND_IMAGE:-leevox/jobweb-backend:latest}"
docker network create jw-seed >/dev/null 2>&1 || true
docker rm -f jw-seed-db >/dev/null 2>&1 || true
docker run -d --name jw-seed-db --network jw-seed -e POSTGRES_USER=jobweb -e POSTGRES_PASSWORD=jobweb -e POSTGRES_DB=jobweb postgres:16.6-alpine >/dev/null
until docker exec jw-seed-db pg_isready -U jobweb -d jobweb -h 127.0.0.1 >/dev/null 2>&1; do sleep 1; done
sleep 2
docker run --rm --network jw-seed -e DATABASE_URL=postgresql+psycopg://jobweb:jobweb@jw-seed-db/jobweb \
  -v "$DATA":/app/jobunicorn/data:ro "$IMG" python -m scripts.import_dataset
docker exec jw-seed-db pg_dump -U jobweb -d jobweb -Fc -Z 6 > "$HERE/assets/jobweb.dump"
docker rm -f jw-seed-db >/dev/null; docker network rm jw-seed >/dev/null
ls -lh "$HERE/assets/jobweb.dump"
