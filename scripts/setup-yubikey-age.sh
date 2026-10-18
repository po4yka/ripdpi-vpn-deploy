#!/usr/bin/env bash
# Enroll or resume one selected hardware age identity. --generate is explicit.
# The companion keeps existing recipients and verifies staged SOPS ciphertext.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "${REPO_ROOT}/scripts/setup_yubikey_age.py" "$@"
