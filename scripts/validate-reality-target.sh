#!/usr/bin/env bash
# Read-only point-in-time TLS/HTTP hygiene; never establishes filtered survival.
# TARGET=host:port SERVER_NAMES='a.example,b.example' (or encrypted SOPS_FILE).
# TARGET_MODE=owned-public requires PUBLIC_ENDPOINT and exact OWNED_SNI.
# PROBE_TIMEOUT=12 VALIDATION_TIMEOUT=120 bound operations and the entire run.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "${REPO_ROOT}/scripts/reality_target_validation.py" validate "$@"
