#!/usr/bin/env bash
# Apply the same private saved-plan snapshot that passed repository policy.
set -euo pipefail
IFS=$'\n\t'
umask 077

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROVIDER="${PROVIDER:-upcloud}"
ENV="${ENV:-prod}"
export PROVIDER ENV

case "$PROVIDER" in
upcloud | hetzner | vultr | scaleway) ;;
*) printf 'unsupported PROVIDER: %s\n' "$PROVIDER" >&2; exit 2 ;;
esac
[[ "$ENV" =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ ]] || {
  printf 'ENV must contain only letters, numbers, and hyphens\n' >&2
  exit 2
}
[[ $# -eq 1 && "$1" == "${ENV}.tfplan" ]] || {
  printf 'expected the saved plan for ENV: %s.tfplan\n' "$ENV" >&2
  exit 2
}
PLAN_SOURCE="${REPO_ROOT}/terraform/providers/${PROVIDER}/$1"
[[ -f "$PLAN_SOURCE" && ! -L "$PLAN_SOURCE" ]] || {
  printf 'saved plan is missing or is not a regular non-symlink file\n' >&2
  exit 1
}

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/tf-apply-policy.XXXXXX")"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

PLAN_COPY="${TMP_DIR}/saved.tfplan"
PLAN_JSON="${TMP_DIR}/plan.json"
cp "$PLAN_SOURCE" "$PLAN_COPY"
"${REPO_ROOT}/scripts/terraform-env.sh" show -json "$PLAN_COPY" >"$PLAN_JSON"
python3 "${REPO_ROOT}/scripts/terraform-plan-policy.py" "$PLAN_JSON"
"${REPO_ROOT}/scripts/terraform-env.sh" apply "$PLAN_COPY"
