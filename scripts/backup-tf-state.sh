#!/usr/bin/env bash
# age-encrypted snapshot of Terraform state. The state file is the only
# durable record for blue-green replacement; losing it forces manual
# `terraform import`. Run this from cron after every successful `make apply`.
#
# Usage:
#   scripts/backup-tf-state.sh                 # uses default destination
#   BACKUP_DEST=/path/to/dir scripts/backup-tf-state.sh
#
# Requires: age, python3, and AGE_RECIPIENT (or AGE_RECIPIENT_FILE).
set -euo pipefail
umask 077

PROVIDER="${PROVIDER:-upcloud}"
ENV="${ENV:-prod}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TF_DIR="${REPO_ROOT}/terraform/providers/${PROVIDER}"

case "$PROVIDER" in
  upcloud|hetzner|vultr|scaleway) ;;
  *) echo "unsupported PROVIDER: $PROVIDER" >&2; exit 2 ;;
esac

if [[ ! "$ENV" =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ ]]; then
  echo "ENV must contain only letters, numbers, and hyphens: $ENV" >&2
  exit 2
fi

if [[ "$ENV" == "prod" ]]; then
  # Legacy production deployments intentionally remain in Terraform's default
  # workspace so adopting environment workspaces does not require a state move.
  STATE_FILE="${TF_DIR}/terraform.tfstate"
else
  STATE_FILE="${TF_DIR}/terraform.tfstate.d/${ENV}/terraform.tfstate"
fi

BACKUP_DEST="${BACKUP_DEST:-${HOME}/.config/vpn-provision/state-backups}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${BACKUP_DEST}/${PROVIDER}-${ENV}-${TIMESTAMP}.tfstate.age"

command -v age >/dev/null 2>&1 || { echo "missing: age" >&2; exit 1; }

if [[ ! -f "$STATE_FILE" ]]; then
  echo "no state file at $STATE_FILE — nothing to back up" >&2
  exit 1
fi

# Recipient resolution priority: AGE_RECIPIENT env > AGE_RECIPIENT_FILE > age.key
RECIPIENTS=()
if [[ -n "${AGE_RECIPIENT:-}" ]]; then
  while IFS= read -r r; do RECIPIENTS+=(-r "$r"); done < <(echo "$AGE_RECIPIENT" | tr ',' '\n')
elif [[ -n "${AGE_RECIPIENT_FILE:-}" ]]; then
  RECIPIENTS+=(-R "$AGE_RECIPIENT_FILE")
elif [[ -f "${HOME}/.config/vpn-provision/age.key" ]]; then
  PUBKEY="$(grep '^# public key:' "${HOME}/.config/vpn-provision/age.key" | awk '{print $4}')"
  if [[ -n "$PUBKEY" ]]; then
    RECIPIENTS+=(-r "$PUBKEY")
  fi
fi

if [[ ${#RECIPIENTS[@]} -eq 0 ]]; then
  echo "no age recipients found; set AGE_RECIPIENT or AGE_RECIPIENT_FILE" >&2
  exit 1
fi

mkdir -p "$BACKUP_DEST"
chmod 0700 "$BACKUP_DEST"

# Incomplete ciphertext never has a name accepted by the recovery selector.
# Register cleanup before creating the invocation-owned private sibling.
temporary=""
trap '[[ -z "$temporary" ]] || rm -f -- "$temporary"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
trap 'exit 131' QUIT
temporary="$(mktemp "${BACKUP_DEST}/.state-backup.XXXXXXXXXX")"
age "${RECIPIENTS[@]}" "$STATE_FILE" > "$temporary"
# A same-directory hard link publishes complete bytes atomically and refuses
# same-second collisions instead of replacing an existing recovery snapshot.
python3 - "$temporary" "$OUT" <<'PY_PUBLISH'
import os
import sys

source, destination = sys.argv[1:]
with open(source, "rb") as ciphertext:
    os.fsync(ciphertext.fileno())
os.link(source, destination, follow_symlinks=False)
os.unlink(source)
parent = os.open(os.path.dirname(destination), os.O_RDONLY | os.O_DIRECTORY)
try:
    os.fsync(parent)
finally:
    os.close(parent)
PY_PUBLISH
temporary=""

echo "wrote $OUT"

# Retain last 30 backups per (provider, env) tuple.
# Match the complete timestamp so an environment prefix cannot select siblings.
# SC2012: `ls -1t` is needed for mtime-ordered listing portable across
# Linux and macOS without GNU coreutils; `find -printf` is GNU-only.
# shellcheck disable=SC2012
ls -1t "${BACKUP_DEST}/${PROVIDER}-${ENV}-"[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z.tfstate.age 2>/dev/null \
  | tail -n +31 \
  | while read -r old; do
      rm -f "$old"
      echo "removed old backup $old"
    done
