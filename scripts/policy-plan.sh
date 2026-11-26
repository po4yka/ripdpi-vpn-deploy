#!/usr/bin/env bash
# Evaluate and optionally apply the same private snapshot of a saved plan.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROVIDER="${PROVIDER:-upcloud}"
ENV="${ENV:-prod}"
case "$PROVIDER" in upcloud|hetzner|vultr|scaleway) ROOT_DIR="terraform/providers/${PROVIDER}" ;; egress-proxy) ROOT_DIR="terraform/ops/${PROVIDER}" ;; *) exit 2 ;; esac
[[ "$ENV" =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ ]] || exit 2
[[ $# == 1 && ( "$1" == check || "$1" == apply ) ]] || {
  echo 'usage: policy-plan.sh check|apply' >&2
  exit 2
}
# A saved plan keeps the configuration it was made from, so refuse here too:
# terraform-env.sh cannot see an override that is gone when the plan is applied.
for override in _destroy_override.tf _observability_cleanup_override.tf; do
  [[ ! -e "${REPO_ROOT}/${ROOT_DIR}/${override}" ]] || {
    echo "refusing: ${ROOT_DIR}/${override} disables prevent_destroy; a destroy is running or crashed" >&2
    exit 1
  }
done
PLAN_SOURCE="${TF_PLAN_FILE:-${REPO_ROOT}/${ROOT_DIR}/${ENV}.tfplan}"
[[ "$PLAN_SOURCE" == /* ]] || { echo 'TF_PLAN_FILE must be absolute' >&2; exit 2; }
[[ -f "$PLAN_SOURCE" && ! -L "$PLAN_SOURCE" ]] || {
  echo 'saved plan is missing or is not a regular non-symlink file' >&2
  exit 1
}
umask 077
work="$(mktemp -d "${TMPDIR:-/tmp}/vpn-policy-plan.XXXXXX")"
trap 'rm -rf -- "$work"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# Resolve an absolute path before Terraform changes its working directory.
work="$(cd "$work" && pwd -P)"
cp "$PLAN_SOURCE" "$work/plan.tfplan"
chmod 0400 "$work/plan.tfplan"
export PROVIDER ENV
"$REPO_ROOT/scripts/terraform-env.sh" show -json "$work/plan.tfplan" |
  "$REPO_ROOT/scripts/check-tf-plan.sh" -
if [[ "$1" == apply ]]; then
  "$REPO_ROOT/scripts/terraform-env.sh" apply "$work/plan.tfplan"
  # An applied plan is stale and can hold provider-generated credentials. A file
  # that changed since the snapshot is another plan and stays.
  if cmp -s -- "$PLAN_SOURCE" "$work/plan.tfplan"; then
    rm -f -- "$PLAN_SOURCE"
  fi
fi
