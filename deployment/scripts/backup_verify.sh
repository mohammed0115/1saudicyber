#!/usr/bin/env bash
# Create and verify PostgreSQL + private-media backups for Cyber-5.
# A failed command can only leave *.partial files, never a backup marked complete.
set -Eeuo pipefail
umask 077

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
MODE="backup"
VERIFY_FILE=""

compose() { docker compose --project-directory "$ROOT_DIR" "$@"; }

usage() {
  cat <<'EOF'
Usage: deployment/scripts/backup_verify.sh [--backup] [--verify FILE.sql.gz] [--verify-media FILE.tar.gz] [--dry-run]

--backup                    Create an atomic PostgreSQL and private-media backup.
--verify FILE.sql.gz        Verify a PostgreSQL dump without restoring it.
--verify-media FILE.tar.gz  Verify a private-media archive without restoring it.
--dry-run                   Show commands without creating files.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backup) MODE="backup" ;;
    --verify) MODE="verify_sql"; VERIFY_FILE="${2:?missing SQL backup path}"; shift ;;
    --verify-media) MODE="verify_media"; VERIFY_FILE="${2:?missing media backup path}"; shift ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

verify_sql() {
  [[ -s "$1" ]] || { echo "SQL backup is empty or missing: $1" >&2; return 1; }
  gzip -t "$1"
  # pg_dump always emits this header; reject gzip files that are empty or contain
  # a proxy/error response instead of a real dump.
  gzip -cd "$1" | head -200 | grep -q 'PostgreSQL database dump'
}

verify_media() {
  [[ -s "$1" ]] || { echo "Media backup is empty or missing: $1" >&2; return 1; }
  tar -tzf "$1" >/dev/null
}

if [[ "$MODE" == "verify_sql" ]]; then
  verify_sql "$VERIFY_FILE"
  echo "VERIFY SQL OK: $VERIFY_FILE"
  exit 0
fi
if [[ "$MODE" == "verify_media" ]]; then
  verify_media "$VERIFY_FILE"
  echo "VERIFY MEDIA OK: $VERIFY_FILE"
  exit 0
fi

mkdir -p "$BACKUP_DIR"
ts="$(date -u +%Y%m%dT%H%M%SZ)"
sql="$BACKUP_DIR/cyber5_${ts}.sql.gz"
media="$BACKUP_DIR/cyber5_private_media_${ts}.tar.gz"
sql_tmp="${sql}.partial"
media_tmp="${media}.partial"
checksum_tmp="$BACKUP_DIR/cyber5_${ts}.sha256.partial"

cleanup() {
  rm -f "$sql_tmp" "$media_tmp" "$checksum_tmp"
}
trap cleanup ERR INT TERM

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  cat <<EOF
Would write temporary files:
  $sql_tmp
  $media_tmp
Would run:
  docker compose --project-directory $ROOT_DIR exec -T db sh -ec 'exec pg_dump -U "\$POSTGRES_USER" -d "\$POSTGRES_DB"' | gzip -9 > $sql_tmp
  docker compose --project-directory $ROOT_DIR exec -T web sh -ec 'test -d /app/private_media && exec tar -C /app/private_media -czf - .' > $media_tmp
Then verify, atomically rename, and write SHA-256 checksums.
EOF
  exit 0
fi

# Commands are streamed straight into temporary archives. With pipefail enabled,
# an unavailable container, bad credentials, or pg_dump failure aborts the run.
compose exec -T db sh -ec 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' | gzip -9 > "$sql_tmp"
compose exec -T web sh -ec 'test -d /app/private_media && exec tar -C /app/private_media -czf - .' > "$media_tmp"

verify_sql "$sql_tmp"
verify_media "$media_tmp"
mv -f "$sql_tmp" "$sql"
mv -f "$media_tmp" "$media"
sha256sum "$sql" "$media" > "$checksum_tmp"
mv -f "$checksum_tmp" "$BACKUP_DIR/cyber5_${ts}.sha256"
trap - ERR INT TERM

printf 'BACKUP OK\nSQL: %s\nPRIVATE_MEDIA: %s\nCHECKSUM: %s\n' \
  "$sql" "$media" "$BACKUP_DIR/cyber5_${ts}.sha256"
