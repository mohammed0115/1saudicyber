#!/usr/bin/env bash
#
# Phase 8D-3A-TOOLING — Unified Safe Deployment Script (1SaudiCyber)
# Platform owned and operated by Get Solution Company / شركة احصل الحل.
#
# Replaces the repeated copy/paste manual deployment workflow with ONE guarded,
# auditable, Bash-first command. It is deliberately simple and explicit so it can
# be inspected line by line.
#
# SAFETY:
#   * --dry-run performs ONLY non-mutating checks and prints what would run.
#   * Execute mode REFUSES to run without --yes.
#   * It NEVER auto-rolls-back, NEVER runs seed/QA commands, NEVER force-resets git,
#     NEVER removes volumes. Every mutating step is preceded by fail-fast gates.
#
# Usage:
#   ./deployment/scripts/safe_manual_deploy.sh \
#       --target <commit-sha> --phase <phase-name> --branch cybertrust-execution \
#       --domain https://cyber-5.com --project-path /opt/1saudicyber [--dry-run|--yes]
#
set -euo pipefail

# ----------------------------------------------------------------------------
# Defaults
# ----------------------------------------------------------------------------
TARGET=""
PHASE=""
BRANCH="cybertrust-execution"
DOMAIN="https://cyber-5.com"
PROJECT_PATH="/opt/1saudicyber"
MEDIA_VOLUME="1saudicyber_media_volume"
BACKUP_BASE="/root/1saudicyber-deploy-backups"
DRY_RUN=0
ASSUME_YES=0

STAMP="$(date -u +%Y%m%d_%H%M%SZ)"

# ----------------------------------------------------------------------------
# Arg parsing
# ----------------------------------------------------------------------------
usage() {
  sed -n '2,30p' "$0"
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)        TARGET="${2:-}"; shift 2 ;;
    --phase)         PHASE="${2:-}"; shift 2 ;;
    --branch)        BRANCH="${2:-}"; shift 2 ;;
    --domain)        DOMAIN="${2:-}"; shift 2 ;;
    --project-path)  PROJECT_PATH="${2:-}"; shift 2 ;;
    --media-volume)  MEDIA_VOLUME="${2:-}"; shift 2 ;;
    --backup-base)   BACKUP_BASE="${2:-}"; shift 2 ;;
    --dry-run)       DRY_RUN=1; shift ;;
    --yes)           ASSUME_YES=1; shift ;;
    -h|--help)       usage 0 ;;
    *) echo "Unknown argument: $1" >&2; usage 1 ;;
  esac
done

# ----------------------------------------------------------------------------
# Output helpers + report buffer
# ----------------------------------------------------------------------------
REPORT_LINES=()
NOTES=()
FINAL_STATUS="GO"

log()  { echo -e "$*"; }
ok()   { echo -e "  [ OK ] $*"; }
info() { echo -e "  [INFO] $*"; }
add_report() { REPORT_LINES+=("$*"); }
add_note()   { NOTES+=("$*"); }

# Mark the run NO-GO and abort (after attempting to still write the report).
fail() {
  FINAL_STATUS="NO-GO"
  add_note "GATE FAILED: $*"
  echo -e "  [FAIL] $*" >&2
  write_report || true
  echo -e "\nDEPLOY ABORTED — final status: NO-GO" >&2
  exit 1
}

# Run a mutating command, or just print it in dry-run.
run_mutating() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    info "(dry-run) would run: $*"
    return 0
  fi
  echo -e "  [RUN ] $*"
  "$@"
}

# Same, but for a shell pipeline string (needs eval). Used sparingly.
run_mutating_sh() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    info "(dry-run) would run: $1"
    return 0
  fi
  echo -e "  [RUN ] $1"
  bash -c "$1"
}

# ----------------------------------------------------------------------------
# Required-arg validation
# ----------------------------------------------------------------------------
[[ -n "$TARGET" ]] || fail "--target <commit-sha> is required"
[[ -n "$PHASE"  ]] || fail "--phase <phase-name> is required"
if [[ ! "$TARGET" =~ ^[0-9a-fA-F]{7,40}$ ]]; then
  fail "target '$TARGET' is not a valid git commit sha (gate 5)"
fi
if [[ "$DRY_RUN" -eq 0 && "$ASSUME_YES" -eq 0 ]]; then
  fail "execute mode requires --yes (refusing to run). Use --dry-run to preview."
fi

MODE="EXECUTE"; [[ "$DRY_RUN" -eq 1 ]] && MODE="DRY-RUN"
BACKUP_DIR="${BACKUP_BASE}/${PHASE}_${STAMP}"
REPORT_DIR="$(cd "$(dirname "$0")/../reports" 2>/dev/null && pwd || echo "$PROJECT_PATH/deployment/reports")"
REPORT_PATH="${REPORT_DIR}/safe_manual_deploy_${PHASE}_${STAMP}.md"

GIT_HEAD_BEFORE=""
GIT_HEAD_AFTER=""
ROLLBACK_COMMIT=""
DB_BACKUP_PATH=""
DB_BACKUP_SIZE="0"
MEDIA_BACKUP_PATH=""
MEDIA_BACKUP_SIZE="0"
BUILD_STATUS="skipped"
CHECK_STATUS="skipped"
MAKEMIGRATIONS_STATUS="skipped"
MIGRATE_STATUS="skipped"
COLLECTSTATIC_STATUS="skipped"
DOCKER_PS_STATUS="skipped"
SMOKE_TABLE=()
LEAK_RESULT="not-run"
CLAIMS_RESULT="not-run"

log "============================================================"
log " 1SaudiCyber — Safe Manual Deploy  (Get Solution Company)"
log "   mode=${MODE}  phase=${PHASE}  target=${TARGET}"
log "   branch=${BRANCH}  domain=${DOMAIN}  project=${PROJECT_PATH}"
log "============================================================"

# ----------------------------------------------------------------------------
# write_report — always emit a markdown report (called on success AND failure)
# ----------------------------------------------------------------------------
write_report() {
  mkdir -p "$REPORT_DIR" 2>/dev/null || true
  {
    echo "# Safe Manual Deploy Report — ${PHASE}"
    echo
    echo "- mode: ${MODE}"
    echo "- phase: ${PHASE}"
    echo "- target commit: ${TARGET}"
    echo "- rollback commit: ${ROLLBACK_COMMIT:-${GIT_HEAD_BEFORE:-unknown}}"
    echo "- branch: ${BRANCH}"
    echo "- domain: ${DOMAIN}"
    echo "- project path: ${PROJECT_PATH}"
    echo "- backup dir: ${BACKUP_DIR}"
    echo "- timestamp (UTC): ${STAMP}"
    echo
    echo "## Git"
    echo "- HEAD before: ${GIT_HEAD_BEFORE:-unknown}"
    echo "- HEAD after: ${GIT_HEAD_AFTER:-unknown}"
    echo
    echo "## Backups"
    echo "- DB backup path: ${DB_BACKUP_PATH:-none}"
    echo "- DB backup size (bytes): ${DB_BACKUP_SIZE}"
    echo "- media backup path: ${MEDIA_BACKUP_PATH:-none}"
    echo "- media backup size (bytes): ${MEDIA_BACKUP_SIZE}"
    echo
    echo "## Deploy steps"
    echo "- docker build web: ${BUILD_STATUS}"
    echo "- manage.py check: ${CHECK_STATUS}"
    echo "- makemigrations --check --dry-run: ${MAKEMIGRATIONS_STATUS}"
    echo "- migrate: ${MIGRATE_STATUS}"
    echo "- collectstatic: ${COLLECTSTATIC_STATUS}"
    echo "- docker compose ps: ${DOCKER_PS_STATUS}"
    echo
    echo "## Smoke checks"
    echo "| path | expected | got | result |"
    echo "|------|----------|-----|--------|"
    for row in "${SMOKE_TABLE[@]:-}"; do [[ -n "$row" ]] && echo "$row"; done
    echo
    echo "## Scans"
    echo "- leak scan: ${LEAK_RESULT}"
    echo "- unsafe claims scan: ${CLAIMS_RESULT}"
    echo
    echo "## Notes"
    if [[ ${#NOTES[@]} -eq 0 ]]; then echo "- none"; else
      for n in "${NOTES[@]}"; do echo "- $n"; done
    fi
    echo
    echo "## Final status"
    echo "**${FINAL_STATUS}**"
    echo
    echo "## Manual rollback instructions (run by a human; this script never auto-rolls-back)"
    echo '```bash'
    echo "cd ${PROJECT_PATH}"
    echo "git checkout ${ROLLBACK_COMMIT:-${GIT_HEAD_BEFORE:-<previous_commit>}}"
    echo "docker compose build web"
    echo "docker compose up -d --force-recreate web"
    echo "sleep 30"
    echo "docker compose ps"
    echo "curl -I ${DOMAIN}/healthz/"
    echo '```'
  } > "$REPORT_PATH"
  info "Report written: $REPORT_PATH"
}

# ----------------------------------------------------------------------------
# GATE 1 — project path exists
# ----------------------------------------------------------------------------
log "\n--- Gates: environment ---"
[[ -d "$PROJECT_PATH" ]] || fail "project path does not exist: $PROJECT_PATH (gate 1)"
cd "$PROJECT_PATH"
ok "project path exists; cwd=$PROJECT_PATH"

# GATE 2 — is a git repository
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail "not a git repository: $PROJECT_PATH (gate 2)"
ok "git repository detected"

# GATE 3 — branch is the expected branch
CURRENT_BRANCH="$(git branch --show-current)"
[[ "$CURRENT_BRANCH" == "$BRANCH" ]] || fail "current branch '$CURRENT_BRANCH' != expected '$BRANCH' (gate 3)"
ok "on expected branch: $BRANCH"

# GATE 4 — clean working tree
if [[ -n "$(git status --short)" ]]; then
  fail "git working tree is not clean (gate 4)"
fi
ok "git working tree clean"

GIT_HEAD_BEFORE="$(git rev-parse HEAD)"
ROLLBACK_COMMIT="$GIT_HEAD_BEFORE"
add_report "git head before: $GIT_HEAD_BEFORE"

# GATE 5/6/7 — target valid, equals origin/<branch>, and HEAD is its ancestor
run_mutating git fetch origin "$BRANCH" --quiet || add_note "git fetch failed or skipped (offline?)"
git cat-file -e "${TARGET}^{commit}" 2>/dev/null || fail "target commit not found in repo: $TARGET (gate 5)"
ok "target commit exists"

ORIGIN_SHA="$(git rev-parse "origin/${BRANCH}" 2>/dev/null || echo '')"
TARGET_SHA="$(git rev-parse "${TARGET}^{commit}" 2>/dev/null || echo '')"
if [[ -z "$ORIGIN_SHA" ]]; then
  fail "cannot resolve origin/${BRANCH} (gate 6)"
fi
if [[ "$TARGET_SHA" != "$ORIGIN_SHA" ]]; then
  fail "target ($TARGET_SHA) != origin/${BRANCH} ($ORIGIN_SHA) (gate 6)"
fi
ok "target equals origin/${BRANCH}"

if ! git merge-base --is-ancestor "$GIT_HEAD_BEFORE" "$TARGET_SHA"; then
  fail "current HEAD is not an ancestor of target — not a fast-forward (gate 7)"
fi
ok "HEAD is an ancestor of target (fast-forward safe)"

# GATE 8 — docker compose available
if ! docker compose version >/dev/null 2>&1; then
  fail "docker compose is unavailable (gate 8)"
fi
ok "docker compose available"

# GATE 9 — db container reachable/healthy
if ! docker compose ps db 2>/dev/null | grep -qiE "up|running|healthy"; then
  fail "db container is not running/healthy (gate 9)"
fi
ok "db container reachable"

# ----------------------------------------------------------------------------
# Backups
# ----------------------------------------------------------------------------
log "\n--- Backups ---"
run_mutating mkdir -p "$BACKUP_DIR"

if [[ "$DRY_RUN" -eq 1 ]]; then
  info "(dry-run) would back up git metadata, docker ps, DB (pg_dump), and media volume into: $BACKUP_DIR"
  DB_BACKUP_PATH="${BACKUP_DIR}/pre_deploy_${STAMP}.sql (dry-run)"
  MEDIA_BACKUP_PATH="${BACKUP_DIR}/media_volume_pre_deploy_${STAMP}.tar.gz (dry-run)"
else
  # Git + docker metadata snapshots.
  git rev-parse HEAD            > "${BACKUP_DIR}/pre_deploy_git_head_${STAMP}.txt"
  git status --short            > "${BACKUP_DIR}/pre_deploy_git_status_${STAMP}.txt" || true
  git log --oneline -n 20       > "${BACKUP_DIR}/pre_deploy_git_log_${STAMP}.txt" || true
  docker compose ps             > "${BACKUP_DIR}/pre_deploy_docker_ps_${STAMP}.txt" || true
  ok "git/docker metadata captured"

  # GATE 10 — DB backup non-zero
  DB_BACKUP_PATH="${BACKUP_DIR}/pre_deploy_${STAMP}.sql"
  docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$DB_BACKUP_PATH" \
    || fail "DB pg_dump command failed (gate 10)"
  test -s "$DB_BACKUP_PATH" || fail "DB backup file is missing or zero bytes (gate 10)"
  DB_BACKUP_SIZE="$(wc -c < "$DB_BACKUP_PATH" | tr -d ' ')"
  ok "DB backup OK (${DB_BACKUP_SIZE} bytes): $DB_BACKUP_PATH"

  # GATE 11 — media backup non-zero
  MEDIA_BACKUP_PATH="${BACKUP_DIR}/media_volume_pre_deploy_${STAMP}.tar.gz"
  docker run --rm \
    -v "${MEDIA_VOLUME}":/media:ro \
    -v "${BACKUP_DIR}":/backup \
    postgres:16-alpine \
    sh -c "tar -czf /backup/media_volume_pre_deploy_${STAMP}.tar.gz -C /media ." \
    || fail "media volume backup failed (gate 11)"
  test -s "$MEDIA_BACKUP_PATH" || fail "media backup file is missing or zero bytes (gate 11)"
  MEDIA_BACKUP_SIZE="$(wc -c < "$MEDIA_BACKUP_PATH" | tr -d ' ')"
  ok "media backup OK (${MEDIA_BACKUP_SIZE} bytes): $MEDIA_BACKUP_PATH"
fi

# ----------------------------------------------------------------------------
# Deploy (mutating). All gated; dry-run prints only.
# ----------------------------------------------------------------------------
log "\n--- Deploy ---"
run_mutating git pull --ff-only origin "$BRANCH" || fail "git pull --ff-only failed (gate 7)"

if run_mutating docker compose build web; then BUILD_STATUS="ok"; else BUILD_STATUS="failed"; fail "docker compose build web failed (gate 12)"; fi

if run_mutating docker compose run --rm web python manage.py check; then CHECK_STATUS="ok"; else CHECK_STATUS="failed"; fail "manage.py check failed (gate 13)"; fi

if run_mutating docker compose run --rm web python manage.py makemigrations --check --dry-run; then MAKEMIGRATIONS_STATUS="ok"; else MAKEMIGRATIONS_STATUS="failed"; fail "makemigrations --check --dry-run reported changes (gate 14)"; fi

if run_mutating docker compose run --rm web python manage.py migrate; then MIGRATE_STATUS="ok"; else MIGRATE_STATUS="failed"; fail "migrate failed (gate 15)"; fi

if run_mutating docker compose run --rm web python manage.py collectstatic --noinput; then COLLECTSTATIC_STATUS="ok"; else COLLECTSTATIC_STATUS="failed"; fail "collectstatic failed (gate 16)"; fi

run_mutating docker compose up -d --force-recreate web || fail "docker compose up --force-recreate web failed (gate 17)"

if [[ "$DRY_RUN" -eq 0 ]]; then
  info "waiting 30s for web container to settle..."
  sleep 30
  docker compose ps && DOCKER_PS_STATUS="captured" || true
  docker compose logs --tail=120 web || true
  GIT_HEAD_AFTER="$(git rev-parse HEAD)"
  # GATE 17 — web container healthy after recreate
  if ! docker compose ps web 2>/dev/null | grep -qiE "up|running|healthy"; then
    fail "web container is not running/healthy after recreate (gate 17)"
  fi
  ok "web container running after recreate"
else
  GIT_HEAD_AFTER="$TARGET_SHA (dry-run: not applied)"
fi

# ----------------------------------------------------------------------------
# Smoke checks
# ----------------------------------------------------------------------------
log "\n--- Smoke checks ---"
# path|kind  (public=must be 200; protected=302/403 ok, never 5xx/404)
SMOKE_SPEC=(
  "/|public"
  "/healthz/|public"
  "/login/|public"
  "/privacy/|public"
  "/terms/|public"
  "/auditors/register/|public"
  "/platform-admin/auditors/|protected"
  "/compliance/classification/|protected"
  "/compliance/dashboard/|protected"
)

http_code() {
  # Prints the HTTP status code (or 000 if unreachable). Never mutating.
  curl -s -o /dev/null -w "%{http_code}" --max-time 20 "$1" 2>/dev/null || echo "000"
}

smoke_ok() {
  local code="$1" kind="$2"
  case "$code" in
    500|502|503|504|404|000) return 1 ;;
  esac
  if [[ "$kind" == "public" ]]; then
    [[ "$code" == "200" ]]
  else
    [[ "$code" == "200" || "$code" == "302" || "$code" == "403" ]]
  fi
}

SMOKE_FAILED=0
for spec in "${SMOKE_SPEC[@]}"; do
  path="${spec%%|*}"; kind="${spec##*|}"
  url="${DOMAIN}${path}"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    info "(dry-run) would smoke: $url ($kind)"
    SMOKE_TABLE+=("| ${path} | ${kind} | (dry-run) | skipped |")
    continue
  fi
  code="$(http_code "$url")"
  if smoke_ok "$code" "$kind"; then
    ok "smoke ${path} -> ${code}"
    SMOKE_TABLE+=("| ${path} | ${kind} | ${code} | OK |")
  else
    add_note "smoke ${path} returned unacceptable status ${code}"
    SMOKE_TABLE+=("| ${path} | ${kind} | ${code} | FAIL |")
    SMOKE_FAILED=1
  fi
done
[[ "$SMOKE_FAILED" -eq 0 ]] || fail "one or more smoke checks returned an unacceptable status (gate 18)"

# ----------------------------------------------------------------------------
# Leak scan
# ----------------------------------------------------------------------------
log "\n--- Leak scan ---"
LEAK_PATHS=("/" "/auditors/register/" "/privacy/" "/terms/")
LEAK_TOKENS=("Phase 8C-FIX-C" "reusable public" "Posts to Django" "RTL/LTR safe" "msgid" "{% trans")
LEAK_FOUND=0
if [[ "$DRY_RUN" -eq 1 ]]; then
  LEAK_RESULT="skipped (dry-run)"
  info "(dry-run) would scan ${LEAK_PATHS[*]} for forbidden tokens"
else
  for p in "${LEAK_PATHS[@]}"; do
    body="$(curl -s --max-time 20 "${DOMAIN}${p}" 2>/dev/null || echo '')"
    for t in "${LEAK_TOKENS[@]}"; do
      if grep -qF -- "$t" <<<"$body"; then
        add_note "leak token '$t' found on $p"
        LEAK_FOUND=1
      fi
    done
  done
  if [[ "$LEAK_FOUND" -eq 0 ]]; then LEAK_RESULT="clean"; ok "no leak tokens found"; else LEAK_RESULT="FAIL"; fi
  [[ "$LEAK_FOUND" -eq 0 ]] || fail "leak scan found forbidden template/debug tokens (gate 19)"
fi

# ----------------------------------------------------------------------------
# Unsafe legal/trust claims scan (conservative).
# Positive claims are banned; negated disclaimers are allowed. The scan is
# CONSERVATIVE: a banned phrase preceded by a negation marker (لا/ليس/دون/بدون/no/not)
# in the same line is treated as a safe disclaimer.
# ----------------------------------------------------------------------------
log "\n--- Unsafe claims scan ---"
CLAIM_PATHS=("/" "/auditors/register/" "/privacy/" "/terms/" "/platform-admin/auditors/")
BANNED_CLAIMS=(
  "معتمد من NCA" "معتمد من أرامكو" "معتمد من سابك"
  "اعتماد رسمي" "اعتماد حكومي"
  "certified by NCA" "certified by Aramco" "certified by SABIC"
  "official accreditation" "government accredited" "official certification"
)
CLAIMS_FOUND=0
if [[ "$DRY_RUN" -eq 1 ]]; then
  CLAIMS_RESULT="skipped (dry-run)"
  info "(dry-run) would scan ${CLAIM_PATHS[*]} for banned positive claims"
else
  for p in "${CLAIM_PATHS[@]}"; do
    body="$(curl -s --max-time 20 "${DOMAIN}${p}" 2>/dev/null || echo '')"
    for c in "${BANNED_CLAIMS[@]}"; do
      # Each line that contains the banned phrase but NO negation marker is a positive claim.
      if grep -F -- "$c" <<<"$body" | grep -vqE "لا|ليس|دون|بدون|[Nn]o |[Nn]ot "; then
        add_note "possible unsafe positive claim '$c' on $p (no negation in line)"
        CLAIMS_FOUND=1
      fi
    done
  done
  if [[ "$CLAIMS_FOUND" -eq 0 ]]; then CLAIMS_RESULT="clean"; ok "no unsafe positive claims found"; else CLAIMS_RESULT="FAIL"; fi
  [[ "$CLAIMS_FOUND" -eq 0 ]] || fail "unsafe legal/trust claim scan found banned positive claims (gate 20)"
fi
add_note "claims scan is conservative: a banned phrase on the same line as a negation marker is treated as a safe disclaimer."

# ----------------------------------------------------------------------------
# Done
# ----------------------------------------------------------------------------
if [[ "$DRY_RUN" -eq 1 ]]; then
  FINAL_STATUS="GO (dry-run: no changes applied)"
fi
write_report
log "\n============================================================"
log " Final status: ${FINAL_STATUS}"
log " Report: ${REPORT_PATH}"
log "============================================================"
exit 0
