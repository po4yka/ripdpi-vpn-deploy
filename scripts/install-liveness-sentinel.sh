#!/usr/bin/env bash
# Secure onboarding is implemented once in the Python controller.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "${REPO_ROOT}/scripts/install_liveness_sentinel.py" "$@"
