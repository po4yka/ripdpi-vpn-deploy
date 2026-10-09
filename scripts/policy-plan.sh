#!/usr/bin/env bash
# Evaluate and optionally apply the same private snapshot of a saved plan.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROVIDER="${PROVIDER:-upcloud}"
ENV="${ENV:-prod}"
case "$PROVIDER" in upcloud|hetzner|vultr|scaleway) ;; *) exit 2 ;; esac
[[ "$ENV" =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ ]] || exit 2
[[ $# == 1 && ( "$1" == check || "$1" == apply ) ]] || {
  echo 'usage: policy-plan.sh check|apply' >&2
  exit 2
}
PLAN_SOURCE="${REPO_ROOT}/terraform/providers/${PROVIDER}/${ENV}.tfplan"
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
"$REPO_ROOT/scripts/terraform-env.sh" show -json "$work/plan.tfplan" > "$work/plan.json"
"$REPO_ROOT/scripts/check-tf-plan.sh" "$work/plan.json"
if [[ "$1" == apply ]]; then
  "$REPO_ROOT/scripts/terraform-env.sh" apply "$work/plan.tfplan"
fi
