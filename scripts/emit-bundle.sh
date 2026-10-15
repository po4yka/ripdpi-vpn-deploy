#!/usr/bin/env bash
# Emit a selected-device profile through the shared in-memory materializer.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[[ $# -gt 0 ]] || { echo 'a client name is required' >&2; exit 2; }
client="$1"
shift
exec python3 "${REPO_ROOT}/scripts/client_payload.py" --bundle "$@" -- "$client"
