#!/usr/bin/env bash
# Versioned fleet rotation plan, authenticated survivors and exact-plan resume.
# Usage: scripts/fleet-rotate.sh --plan FILE [--dry-run] [--resume]
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "${REPO_ROOT}/scripts/fleet_rotation.py" "$@"
