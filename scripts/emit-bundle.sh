#!/usr/bin/env bash
# Emit a selected-device profile through the shared in-memory materializer.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[[ $# -gt 0 ]] || { echo 'a client name is required' >&2; exit 2; }
client="$1"
shift
for argument in "$@"; do
  if [[ "$argument" == "--xhttp-only" ]]; then
    echo "--xhttp-only is reserved for monitoring and unsupported in RIPDPI bundles" >&2
    exit 1
  fi
done
exec python3 "${REPO_ROOT}/scripts/client_payload.py" --bundle "$@" -- "$client"
