#!/usr/bin/env bash
# Deprecated compatibility entrypoint.
#
# Production deployments must use the guarded workflow that requires a fixed commit SHA,
# records a report, takes backups, and fails closed on preflight or health-gate errors.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "deploy.sh is a guarded compatibility wrapper; forwarding to safe_manual_deploy.sh."
exec "${SCRIPT_DIR}/scripts/safe_manual_deploy.sh" "$@"
