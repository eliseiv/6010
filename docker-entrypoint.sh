#!/bin/sh
# Entrypoint: apply Alembic migrations, then start Uvicorn.
# Fails fast if migrations fail (set -e) so a broken DB schema never serves traffic.
set -e

echo "[entrypoint] Applying database migrations (alembic upgrade head)..."
alembic upgrade head

echo "[entrypoint] Starting Uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level "$(echo "${LOG_LEVEL:-info}" | tr '[:upper:]' '[:lower:]')"
