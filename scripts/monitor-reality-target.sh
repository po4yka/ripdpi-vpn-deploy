#!/usr/bin/env bash
# Bound the entire read-only observation and owned temporary plaintext lifetime.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "${REPO_ROOT}/scripts/reality_target_monitor.py" probe "$@"
