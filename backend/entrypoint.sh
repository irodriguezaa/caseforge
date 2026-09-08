#!/bin/sh
set -e

mkdir -p /app/data/release_notes

if [ "$(id -u)" = "0" ]; then
  chown -R caseforge:caseforge /app/data/release_notes
  exec su caseforge -s /bin/sh -c 'alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000'
fi

alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
