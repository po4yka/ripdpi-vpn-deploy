#!/usr/bin/env bash
# Re-encrypt the secrets file for a changed recipient list.
# Wrapper around `sops updatekeys` and `sops rotate`: new recipients and a new data key.
set -euo pipefail
umask 077

ENV="${ENV:-prod}"
PROVIDER="${PROVIDER:-upcloud}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOPS_FILE="${SOPS_FILE:-${HOME}/.config/vpn-provision/${ENV}.secrets.sops.yaml}"
SOPS_FILE="$(SOPS_FILE="$SOPS_FILE" python3 -c 'import os; print(os.path.realpath(os.environ["SOPS_FILE"]))')"

if [[ ! -f "$SOPS_FILE" ]]; then
  echo "missing SOPS file: $SOPS_FILE" >&2
  exit 1
fi

# Use the project-wide writer lock shared by new-client, token issuance and
# retirement.  updatekeys rewrites the encrypted document, so running it
# alongside any of those transactions could otherwise resurrect or lose a
# completed client change.
SOPS_LOCK="${SOPS_FILE}.new-client.lock"
[[ ! -L "$SOPS_LOCK" ]] || { echo 'unsafe secrets writer lock' >&2; exit 1; }
exec 9<> "$SOPS_LOCK"
if ! python3 "$REPO_ROOT/scripts/private-operator-lock.py" "$SOPS_LOCK" 9; then
  echo 'error: another secrets transaction is active or its lock is unsafe' >&2
  exit 1
fi

# sops updatekeys reads the recipient list from .sops.yaml or env (SOPS_AGE_RECIPIENTS)
# and wraps the existing data key for it. A removed recipient still holds that
# data key and could decrypt every later version, so the data key is rotated
# too. The file changes only when both steps succeed: any failure, or an
# interrupt, restores the copy taken here.
for stale in "${SOPS_FILE}".rotate.*; do
  [[ ! -e "$stale" ]] || {
    echo "error: a killed rotation left ${stale}; it holds the file from before that run. Compare it with ${SOPS_FILE}, keep the right one, remove the copy and run again" >&2
    exit 1
  }
done
backup="$(mktemp "${SOPS_FILE}.rotate.XXXXXX")"
cp -p -- "$SOPS_FILE" "$backup"
restore() {
  [[ ! -e "$backup" ]] || mv -f -- "$backup" "$SOPS_FILE"
}
trap restore EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if ! sops updatekeys "$SOPS_FILE" || ! sops rotate --in-place "$SOPS_FILE"; then
  echo "error: rotation failed; ${SOPS_FILE} is unchanged" >&2
  exit 1
fi
rm -f -- "$backup"

echo "updated recipients and rotated the data key on $SOPS_FILE"
echo "verify decryption: sops --decrypt $SOPS_FILE > /dev/null"

ENV="$ENV" PROVIDER="$PROVIDER" \
  "${REPO_ROOT}/scripts/audit-log.sh" append-best-effort \
    --action rotate-secrets \
    --note "sops_file=${SOPS_FILE##*/}"
