#!/usr/bin/env bash
# age-encrypted snapshot of the current OpenTofu state, read from the encrypted
# remote backend through scripts/terraform-env.sh. Bucket versions keep the
# state history; this snapshot is the copy that survives losing the bucket or
# the state passphrase. Run it after every successful apply.
#
# Usage:
#   PROVIDER=upcloud ENV=prod scripts/backup-tf-state.sh
#   BACKUP_DEST=/path/to/dir PROVIDER=upcloud ENV=prod scripts/backup-tf-state.sh
#
# Requires: age, python3, AGE_RECIPIENT (or AGE_RECIPIENT_FILE), an initialized
# workspace, and the state identity plus TF_VAR_state_passphrase in the environment.
set -euo pipefail
umask 077

PROVIDER="${PROVIDER:-upcloud}"
ENV="${ENV:-prod}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

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

BACKUP_DEST="${BACKUP_DEST:-${HOME}/.config/vpn-provision/state-backups}"

command -v age >/dev/null 2>&1 || { echo "missing: age" >&2; exit 1; }

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

# Register cleanup before allocating this invocation's private sibling.
pending=""
trap '[[ -z "$pending" ]] || rm -f -- "$pending"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
trap 'exit 131' QUIT
pending="$(mktemp "${BACKUP_DEST}/.state-backup.XXXXXXXXXX")"
# Plaintext state only passes through this pipe; it is validated before age
# seals it, so an empty or broken pull never becomes a recovery snapshot.
PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" state pull \
  | python3 -c '
import json
import sys

data = sys.stdin.buffer.read()
try:
    state = json.loads(data)
    valid = (
        isinstance(state, dict)
        and state.get("version") == 4
        and type(state.get("serial")) is int and state["serial"] >= 0
        and isinstance(state.get("lineage"), str) and bool(state["lineage"])
        and isinstance(state.get("resources"), list)
    )
except ValueError:
    valid = False
if not valid:
    sys.exit("state pull failed, or the current state is empty or invalid; nothing was backed up")
sys.stdout.buffer.write(data)
' \
  | age "${RECIPIENTS[@]}" > "$pending"
python3 - "$pending" <<'PY_SYNC'
import os
import sys

try:
    with open(sys.argv[1], "rb") as ciphertext:
        os.fsync(ciphertext.fileno())
except OSError:
    sys.exit("state backup file sync failed")
PY_SYNC

# A hard link publishes complete ciphertext without overwriting another writer.
# Keep the established timestamp contract and wait at most ten collision retries.
for ((attempt = 0; attempt <= 10; attempt++)); do
  TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  OUT="${BACKUP_DEST}/${PROVIDER}-${ENV}-${TIMESTAMP}.tfstate.age"
  if python3 - "$pending" "$OUT" <<'PYTHON'
import os
import sys

try:
    os.link(sys.argv[1], sys.argv[2], follow_symlinks=False)
except FileExistsError:
    sys.exit(17)
except OSError:
    sys.exit(1)
PYTHON
  then
    break
  else
    publication_status=$?
  fi
  if (( publication_status != 17 || attempt == 10 )); then
    echo 'state backup publication failed; existing backups were retained' >&2
    exit 1
  fi
  sleep 1
done

# Persist both the complete final name and removal of the private staging name.
# A sync failure retains the complete backup but cannot announce success or prune.
python3 - "$pending" "$BACKUP_DEST" <<'PY_SYNC'
import os
import sys

try:
    os.unlink(sys.argv[1])
    parent = os.open(sys.argv[2], os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)
except OSError:
    sys.exit("state backup directory sync failed")
PY_SYNC
pending=""

echo "wrote $OUT"

# Retain the last 30 backups per (provider, env) tuple, and every backup of
# the last 30 days: a count alone lets repeated runs after a bad apply push
# out every good backup.
# Match the complete timestamp so an environment prefix cannot select siblings.
# SC2012: `ls -1t` is needed for mtime-ordered listing portable across
# Linux and macOS without GNU coreutils; `find -printf` is GNU-only.
# shellcheck disable=SC2012
ls -1t "${BACKUP_DEST}/${PROVIDER}-${ENV}-"[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z.tfstate.age 2>/dev/null \
  | tail -n +31 \
  | while read -r old; do
      [[ -n "$(find "$old" -mtime +30)" ]] || continue
      rm -f "$old"
      echo "removed old backup $old"
    done
