#!/usr/bin/env bash
# Emit a selected-device profile through the shared in-memory materializer.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "${REPO_ROOT}/scripts/client_payload.py" --bundle "$@"
