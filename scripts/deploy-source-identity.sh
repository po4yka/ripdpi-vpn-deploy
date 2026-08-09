#!/usr/bin/env bash
# Emit immutable provenance for the files that can change an Ansible deploy.
# The digest is based on Git blob IDs and paths, so documentation-only commits
# keep the same deployable identity while any playbook, role, operator script,
# or Ansible dependency change produces a new value.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:---identity}"
REVISION="$(git -C "$REPO_ROOT" rev-parse --verify 'HEAD^{commit}')"

DIGEST="$({
  git -C "$REPO_ROOT" ls-tree -r -z "$REVISION" -- \
    ansible scripts requirements.yml
} | python3 -c 'import hashlib, sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())')"

case "$MODE" in
  --revision)
    printf '%s\n' "$REVISION"
    ;;
  --digest)
    printf '%s\n' "$DIGEST"
    ;;
  --identity)
    printf '%s %s\n' "$REVISION" "$DIGEST"
    ;;
  *)
    echo "usage: $0 [--identity|--revision|--digest]" >&2
    exit 64
    ;;
esac
