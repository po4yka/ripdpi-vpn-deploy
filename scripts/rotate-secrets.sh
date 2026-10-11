#!/usr/bin/env bash
# Re-encrypt the secrets file under a new age recipient (or after editing).
# Wrapper around `sops updatekeys` + `sops --encrypt`.
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
# and re-encrypts the data key without rewriting the payload.
sops updatekeys "$SOPS_FILE"

echo "updated keys on $SOPS_FILE"
echo "verify decryption: sops --decrypt $SOPS_FILE > /dev/null"

ENV="$ENV" PROVIDER="$PROVIDER" \
  "${REPO_ROOT}/scripts/audit-log.sh" append-best-effort \
    --action rotate-secrets \
    --note "sops_file=${SOPS_FILE##*/}"
