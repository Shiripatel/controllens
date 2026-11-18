#!/bin/sh
# Hosts mount the data disk owned by root. Fix that, then run the app as a normal user.
set -e
DATA_DIR="${CL_DATA_DIR:-/data}"
mkdir -p "$DATA_DIR" "${CL_STORAGE_DIR:-/data/storage}"
if [ "$(id -u)" = "0" ]; then
  chown -R appuser "$DATA_DIR" "${CL_STORAGE_DIR:-/data/storage}" 2>/dev/null || true
  exec runuser -u appuser -- uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips '*'
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips '*'
