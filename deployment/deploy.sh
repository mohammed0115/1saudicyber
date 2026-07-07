#!/usr/bin/env bash
# CyberTrust KSA — safe production deploy (Docker Compose).
#
# Run ON THE SERVER from the repo root:
#     cd /opt/1saudicyber && bash deployment/deploy.sh
#
# It is fail-closed and idempotent. After the P0 hardening the app REFUSES to boot in
# production without a strong DJANGO_SECRET_KEY and explicit ALLOWED_HOSTS, so this script
# validates the environment BEFORE rebuilding — it never rebuilds into a broken state.
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
BRANCH="${BRANCH:-cybertrust-execution}"
ENV_FILE="${APP_DIR}/.env"
cd "$APP_DIR"

say()  { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[warn] %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m[FATAL] %s\033[0m\n' "$*" >&2; exit 1; }

# --- 0) Preconditions ------------------------------------------------------
command -v docker >/dev/null || die "docker not found."
docker compose version >/dev/null 2>&1 || die "'docker compose' plugin not found."
[ -f "$ENV_FILE" ] || die "Missing $ENV_FILE. Copy deployment/docker/env.example to .env and fill it."

# Read a KEY=value from .env without printing secrets.
envval() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- || true; }

# --- 1) Fail-closed environment validation (matches settings.py) ----------
say "Validating environment (fail-closed) ..."
SECRET="$(envval DJANGO_SECRET_KEY)"
if [ -z "$SECRET" ] || [ "$SECRET" = "dev-secret-key-change-in-production" ] || \
   [ "$SECRET" = "replace-with-a-long-random-secret" ]; then
  warn "DJANGO_SECRET_KEY is missing or default."
  GEN="$(openssl rand -base64 48 2>/dev/null | tr -d '\n' || head -c 48 /dev/urandom | base64 | tr -d '\n')"
  die "Set a strong key in .env, e.g.:
       DJANGO_SECRET_KEY=${GEN}
     (do NOT reuse the old exposed one) then re-run."
fi

HOSTS="$(envval ALLOWED_HOSTS)"
case "$HOSTS" in
  ""|"*") die "ALLOWED_HOSTS must list explicit hostnames (no empty, no '*'). e.g. ALLOWED_HOSTS=1saudicyber.com,www.1saudicyber.com" ;;
esac

# Informative-only (not fatal): AI + payment posture.
RESID="$(envval AI_DATA_RESIDENCY_MODE)"; RESID="${RESID:-disabled}"
[ "$RESID" = "external" ] && warn "AI_DATA_RESIDENCY_MODE=external — evidence text WILL be sent to the external LLM." \
                          || say "AI data residency: '${RESID}' (no evidence text leaves the Kingdom)."
PP="$(envval PAYMENT_PROVIDER)"; say "Payment provider: '${PP:-manual}'."

# --- 2) Pull latest code ---------------------------------------------------
say "Pulling ${BRANCH} ..."
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

# --- 3) Build & start (entrypoint self-heals media, migrates, collectstatic) ---
say "Building image (installs Tesseract/poppler — first build is slower) ..."
docker compose build web
say "Starting containers ..."
docker compose up -d

# --- 4) Wait for health ----------------------------------------------------
say "Waiting for web to become healthy ..."
for i in $(seq 1 30); do
  if docker compose ps web | grep -qiE "healthy|running"; then break; fi
  sleep 3
done

# --- 5) Explicit migrate + collectstatic (idempotent; entrypoint already ran them) ---
say "Applying migrations + collecting static (idempotent) ..."
docker compose exec -T web python manage.py migrate --noinput
docker compose exec -T web python manage.py collectstatic --noinput

# --- 6) Load control catalogue --------------------------------------------
# Full official catalogue: 417 controls across 7 frameworks (idempotent, non-destructive).
say "Importing FULL official control catalogue (417 across 7 frameworks) ..."
docker compose exec -T web python manage.py import_all_official_controls --apply || warn "control import skipped/failed — review manually."
say "Tagging conditional controls (cloud/OT/critical/remote/social) ..."
docker compose exec -T web python manage.py tag_conditional_controls --apply || warn "conditional tagging skipped/failed — review manually."

# --- 7) Smoke test ---------------------------------------------------------
say "Smoke test ..."
PORT="$(envval WEB_PORT)"; PORT="${PORT:-8000}"
if curl -fsS -o /dev/null "http://localhost:${PORT}/healthz/"; then
  say "Health check OK (http://localhost:${PORT}/healthz/)."
else
  warn "Health check did not return 200 — inspect: docker compose logs --tail=80 web"
fi

say "Deploy complete. Recent logs:"
docker compose logs --tail=30 web || true

cat <<'NEXT'

------------------------------------------------------------------
POST-DEPLOY CHECKLIST
  * UAT: log in per role (executive / auditor / compliance) — no 500s.
  * Evidence upload: try a .docx (works without OCR) and a scanned PDF (OCR now installed).
  * AI advisory: OFF unless AI_DATA_RESIDENCY_MODE=external in .env (data-sovereignty gate).
  * Create the admin (env-driven, one time):
        docker compose exec -e ADMIN_EMAIL=you@dom.sa -e ADMIN_PASSWORD='<strong>' web python create_admin.py
  * Payments: manual is the default; Moyasar stays gated until keys are added to .env.
  * FULL official control dataset (447) is an owner data step — pilot only ships in-repo.
------------------------------------------------------------------
NEXT
