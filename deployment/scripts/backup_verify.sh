#!/usr/bin/env bash
# Create an application-consistent PostgreSQL backup plus private evidence archive.
# This script never deploys and supports a verification-only restore drill.
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
COMPOSE=(docker compose --project-directory "$ROOT_DIR")
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
MODE="backup"

usage() {
  cat <<'EOF'
Usage: deployment/scripts/backup_verify.sh [--backup] [--verify FILE.sql.gz] [--dry-run]

--backup             Create timestamped PostgreSQL + private-media backups and SHA-256 sums.
--verify FILE.sql.gz Validate gzip integrity and list SQL content without writing to production.
--dry-run            Print the backup commands without executing them.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backup) MODE="backup" ;;
    --verify) MODE="verify"; VERIFY_FILE="${2:?missing backup path}"; shift ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

run() { if [[ "${DRY_RUN:-0}" == "1" ]]; then printf '+ '; printf '%q ' "$@"; printf '\n'; else "$@"; fi; }

if [[ "$MODE" == "verify" ]]; then
  [[ -f "${VERIFY_FILE:-}" ]] || { echo "Backup not found: ${VERIFY_FILE:-}" >&2; exit 2; }
  gzip -t "$VERIFY_FILE"
  # A schema/data dump must contain PostgreSQL statements; this avoids claiming
  # an empty or HTML error response is a valid backup.
  gzip -cd "$VERIFY_FILE" | head -200 | grep -qE 'PostgreSQL database dump|CREATE TABLE|INSERT INTO' || {
    echo "Backup does not look like a PostgreSQL dump." >&2; exit 1;
  }
  echo "VERIFY OK: $VERIFY_FILE"
  exit 0
fi

mkdir -p "$BACKUP_DIR"
ts="$(date -u +%Y%m%dT%H%M%SZ)"
sql="$BACKUP_DIR/cyber5_${ts}.sql.gz"
media="$BACKUP_DIR/cyber5_private_media_${ts}.tar.gz"

# Compose keeps DB credentials in its own environment; pg_dump runs inside db
# so no password appears in shell history or the generated command output.
run bash -c "'${COMPOSE[*]}' exec -T db sh -c 'pg_dump -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\"' | gzip -9 > '$sql'"
run "${COMPOSE[@]}" exec -T web sh -c 'test -d /app/private_media'
run bash -c "'${COMPOSE[*]}' exec -T web tar -C /app/private_media -czf - . > '$media'"

if [[ "${DRY_RUN:-0}" != "1" ]]; then
  gzip -t "$sql"
  tar -tzf "$media" >/dev/null
  sha256sum "$sql" "$media" > "$BACKUP_DIR/cyber5_${ts}.sha256"
  printf 'BACKUP OK\nSQL: %s\nPRIVATE_MEDIA: %s\nCHECKSUM: %s\n' "$sql" "$media" "$BACKUP_DIR/cyber5_${ts}.sha256"
fi
