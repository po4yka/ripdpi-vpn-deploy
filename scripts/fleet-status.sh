#!/usr/bin/env bash
# Passive status for HOSTS provider:environment pairs in the existing inventory.
# Exit 0: recent local watchdog success; 1: incomplete/unhealthy observation;
# 2: local admission failure. Client-path health remains explicitly unknown.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "${REPO_ROOT}/scripts/fleet_status.py" "$@"
