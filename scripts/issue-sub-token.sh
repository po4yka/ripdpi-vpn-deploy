#!/usr/bin/env bash
# Issue/refresh through the locked encrypted exact-payload transaction.
set -euo pipefail
umask 077
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "${REPO_ROOT}/scripts/issue_sub_token.py" "$@"
