#!/usr/bin/env bash
# Run Terraform in the state workspace belonging to PROVIDER + ENV.
#
# Existing production deployments used Terraform's default workspace before
# environments became multi-node. Keep ENV=prod mapped to `default` so that
# adopting this wrapper does not strand the legacy production state. Every
# other environment maps to a workspace with the same name.
#
# Usage:
#   PROVIDER=upcloud ENV=green ./scripts/terraform-env.sh init
#   PROVIDER=upcloud ENV=green ./scripts/terraform-env.sh output -raw server_ipv4
set -euo pipefail

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

TF_DIR="${REPO_ROOT}/terraform/providers/${PROVIDER}"
[[ -d "$TF_DIR" ]] || { echo "missing Terraform root: $TF_DIR" >&2; exit 2; }
[[ $# -gt 0 ]] || { echo "usage: $0 <terraform command> [args...]" >&2; exit 2; }

workspace="$ENV"
[[ "$ENV" == "prod" ]] && workspace="default"
export TF_DATA_DIR="${TF_DIR}/.terraform-env/${workspace}"

tf() {
  terraform "-chdir=${TF_DIR}" "$@"
}

if [[ "$1" == "init" ]]; then
  tf "$@"
  if ! tf workspace select "$workspace" >/dev/null 2>&1; then
    tf workspace new "$workspace"
  fi
  exit 0
fi

if ! tf workspace select "$workspace" >/dev/null 2>&1; then
  echo "Terraform workspace '$workspace' does not exist for ${PROVIDER}/${ENV}; run 'make PROVIDER=${PROVIDER} ENV=${ENV} init' first." >&2
  exit 1
fi

if [[ "$PROVIDER" == "vultr" ]]; then
  case "$1" in
    plan|apply|destroy|import|refresh)
      "${REPO_ROOT}/scripts/check-vultr-control-plane.py"
      ;;
  esac
fi

if [[
  "$PROVIDER" == "vultr" && "$1" == "apply" &&
  "${VULTR_STAGING_MARK_APPLY:-false}" == "true"
]]; then
  [[ "${VULTR_STAGING_PLAN_FD:-}" =~ ^[0-9]+$ ]] || {
    echo "VULTR_STAGING_PLAN_FD must be an open numeric descriptor" >&2
    exit 2
  }
  "${REPO_ROOT}/scripts/vultr-staging-cleanup-guard.py" mark-apply-started \
    --manifest "${VULTR_STAGING_MANIFEST:?VULTR_STAGING_MANIFEST is required}" \
    --evidence-output "${VULTR_STAGING_EVIDENCE:?VULTR_STAGING_EVIDENCE is required}" \
    --fd-number "$VULTR_STAGING_PLAN_FD" \
    --expected-provider vultr \
    --expected-environment "$ENV"
  unset VULTR_STAGING_MARK_APPLY VULTR_STAGING_PLAN_FD \
    VULTR_STAGING_MANIFEST VULTR_STAGING_EVIDENCE
fi

exec terraform "-chdir=${TF_DIR}" "$@"
