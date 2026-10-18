#!/usr/bin/env bash
# age-encrypted snapshot of Terraform state. The state file is the only
# durable record for blue-green replacement; losing it forces manual
# `terraform import`. Run this from cron after every successful `make apply`.
#
# Usage:
#   scripts/backup-tf-state.sh                 # uses default destination
#   BACKUP_DEST=/path/to/dir scripts/backup-tf-state.sh
#
# Requires: age, the AGE_RECIPIENT env var (or AGE_RECIPIENT_FILE).
set -euo pipefail

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

if [[ "$ENV" == "default" ]]; then
  echo 'ENV=default is reserved for the legacy prod workspace; use ENV=prod or a distinct environment' >&2
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

umask 077
pending="$(mktemp "${BACKUP_DEST}/.state-backup.XXXXXXXX")"
trap 'rm -f -- "$pending"' EXIT
trap 'exit 1' HUP INT TERM
age "${RECIPIENTS[@]}" "$STATE_FILE" > "$pending"

# A hard link publishes complete ciphertext without overwriting another writer.
# Keep the established timestamp contract and wait at most ten collision retries.
for ((attempt = 0; attempt <= 10; attempt++)); do
  TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  OUT="${BACKUP_DEST}/${PROVIDER}-${ENV}-${TIMESTAMP}.tfstate.age"
  if python3 - "$pending" "$OUT" <<'PYTHON'
import os
import sys

try:
    os.link(sys.argv[1], sys.argv[2])
except OSError:
    sys.exit(1)
PYTHON
  then
    break
  fi
  if [[ ! -e "$OUT" && ! -L "$OUT" ]] || (( attempt == 10 )); then
    echo 'state backup publication failed; existing backups were retained' >&2
    exit 1
  fi
  sleep 1
done

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
