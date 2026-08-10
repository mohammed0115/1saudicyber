#!/usr/bin/env sh
# CyberTrust KSA — container entrypoint.
# Waits for the database, applies migrations, collects static files, then
# launches Gunicorn. No data is seeded and no superuser is created here
# (those are documented manual steps in the runbook).
set -eu

# --- Self-heal volume ownership, then drop root privileges ---
# Docker named volumes (media_volume, static_volume) keep the uid/gid from when they
# were FIRST created. A stale root-owned media volume makes evidence uploads fail with
# PermissionError. Fix ownership as root on every start, then re-exec this same script
# as the unprivileged app user (uid 10001) via gosu so the app never runs as root.
if [ "$(id -u)" = "0" ]; then
    mkdir -p /app/media /app/staticfiles
    chown -R appuser:appuser /app/media /app/staticfiles
    exec gosu appuser "$0" "$@"
fi

# --- Wait for PostgreSQL (only when POSTGRES_DB is configured) ---
if [ -n "${POSTGRES_DB:-}" ]; then
    host="${POSTGRES_HOST:-db}"
    port="${POSTGRES_PORT:-5432}"
    echo "Waiting for PostgreSQL at ${host}:${port} ..."
    attempts=0
    until python -c "import socket,sys; s=socket.socket(); s.settimeout(2); s.connect(('${host}', ${port}))" 2>/dev/null; do
        attempts=$((attempts + 1))
        if [ "${attempts}" -ge 60 ]; then
            echo "ERROR: database not reachable after 60 attempts; aborting." >&2
            exit 1
        fi
        sleep 2
    done
    echo "PostgreSQL is reachable."
fi

# --- Migrate ---
echo "Applying database migrations ..."
python manage.py migrate --noinput

# --- Collect static files ---
echo "Collecting static files ..."
python manage.py collectstatic --noinput

# --- Launch the app (replace shell with the given command) ---
echo "Starting: $*"
exec "$@"
