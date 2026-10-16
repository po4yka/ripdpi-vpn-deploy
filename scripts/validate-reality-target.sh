#!/usr/bin/env bash
# Bounded local REALITY target TLS/HTTP hygiene. No browser or filtered-path claim.
# TARGET=host:port SERVER_NAMES='name,name2' selects explicit inputs.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "${REPO_ROOT}/scripts/reality_target_validation.py" "$@"
