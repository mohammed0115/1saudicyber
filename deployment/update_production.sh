#!/usr/bin/env bash
# =============================================================================
# 1SaudiCyber — Production update (Docker Compose stack: db/redis/web/worker/beat)
#
# Safe, idempotent update: pull → build → additive migrations → collectstatic →
# rolling restart → health check → auto-rollback on failure.
#
# Usage (on the production host, from the repo root):
#   BRANCH=cybertrust-execution ./deployment/update_production.sh
#
# Pre-reqs: docker + docker compose v2; a real .env (NOT committed) with
#   DEBUG=False, SECRET_KEY, ALLOWED_HOSTS, POSTGRES_*, REDIS_URL,
#   EVIDENCE_ASYNC_ENABLED=True, ENFORCE_ADMIN_MFA=True, and (if used) OPENAI + Moyasar.
# =============================================================================
set -Eeuo pipefail

BRANCH="${BRANCH:-cybertrust-execution}"
COMPOSE="${COMPOSE:-docker compose}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/healthz/}"
HEALTH_RETRIES="${HEALTH_RETRIES:-20}"

log(){ printf '\033[1;32m[deploy]\033[0m %s\n' "$*"; }
err(){ printf '\033[1;31m[deploy:ERROR]\033[0m %s\n' "$*" >&2; }

cd "$(git rev-parse --show-toplevel)"

# 0) Pre-flight ---------------------------------------------------------------
[ -f .env ] || { err "Missing .env on the production host. Copy deployment/docker/env.example and fill real values."; exit 1; }
if grep -qE '^DEBUG=True' .env; then err "DEBUG=True in .env — refuse to deploy to production."; exit 1; fi
if git status --porcelain | grep -q .; then err "Working tree not clean. Commit/stash local changes first."; exit 1; fi
command -v docker >/dev/null || { err "docker not found"; exit 1; }

PREV_REF="$(git rev-parse HEAD)"
log "Current revision: ${PREV_REF:0:10}"

rollback(){
  err "Deployment failed — rolling back to ${PREV_REF:0:10}"
  git reset --hard "$PREV_REF" >/dev/null 2>&1 || true
  $COMPOSE up -d --build web worker beat >/dev/null 2>&1 || true
  err "Rolled back. Investigate logs: $COMPOSE logs --tail=100 web"
}
trap rollback ERR

# 1) Fetch latest code --------------------------------------------------------
log "Fetching origin/$BRANCH ..."
git fetch --prune origin "$BRANCH"
git checkout "$BRANCH"
git reset --hard "origin/$BRANCH"
NEW_REF="$(git rev-parse HEAD)"
log "Updating ${PREV_REF:0:10} -> ${NEW_REF:0:10}"

# 2) Build images -------------------------------------------------------------
log "Building images ..."
$COMPOSE build web worker beat

# 3) Backup DB before migrating (safety) -------------------------------------
log "Backing up the database ..."
$COMPOSE run --rm web python manage.py backup_db --keep-days 14 || err "backup_db warned (continuing)"

# 4) Migrations — MUST be additive-only. Abort if a NEW migration is unexpected.
log "Checking migration plan ..."
$COMPOSE run --rm web python manage.py makemigrations --check --dry-run \
  || { err "Model changes without a migration file — aborting."; exit 1; }
log "Applying migrations (additive) ..."
$COMPOSE run --rm web python manage.py migrate --noinput

# 5) Static assets ------------------------------------------------------------
log "Collecting static ..."
$COMPOSE run --rm web python manage.py collectstatic --noinput

# 6) Deploy-safety checks -----------------------------------------------------
log "Running Django deploy checks ..."
$COMPOSE run --rm -e DJANGO_DEBUG=False web python manage.py check --deploy || err "check --deploy raised warnings (review above)"

# 7) Rolling restart ----------------------------------------------------------
log "Restarting services (web, worker, beat) ..."
$COMPOSE up -d --build web worker beat

# 8) Health check -------------------------------------------------------------
log "Waiting for health at $HEALTH_URL ..."
ok=0
for i in $(seq 1 "$HEALTH_RETRIES"); do
  code="$(curl -fsS -o /dev/null -w '%{http_code}' --max-time 5 "$HEALTH_URL" || true)"
  if [ "$code" = "200" ]; then ok=1; log "Healthy (HTTP 200) after ${i} check(s)."; break; fi
  sleep 3
done
[ "$ok" = "1" ] || { err "Health check never returned 200."; exit 1; }

trap - ERR
log "✅ Deploy complete: ${NEW_REF:0:10}"
log "Post-deploy reminders: verify Celery worker/beat are up (docker compose ps),"
log "and that ENFORCE_ADMIN_MFA=True and EVIDENCE_ASYNC_ENABLED=True are set in .env."
