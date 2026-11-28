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
# State, its backups and saved plans can hold provider-generated credentials.
umask 077

# Cron supplies encrypted documents only to these two public output reads.
# The monitor, its probes and its notification clients never inherit state credentials.
if [[ -n "${MONITOR_STATE_IDENTITY_SOPS_FILE:-}" && "${1:-}" == output ]]; then
  case "$*" in
    "output -raw server_ipv4"|"output -raw service_ipv4"|"output -raw admin_user") ;;
    *) echo "unsupported scheduled state output" >&2; exit 2 ;;
  esac
  printf -v output_command '%q ' "$0" "$@"
  printf -v passphrase_command '%q ' sops exec-env "${STATE_PASSPHRASE_SOPS_FILE:?}" "$output_command"
  identity="$MONITOR_STATE_IDENTITY_SOPS_FILE"
  unset MONITOR_STATE_IDENTITY_SOPS_FILE
  exec sops exec-env "$identity" "$passphrase_command"
fi

PROVIDER="${PROVIDER:-upcloud}"
ENV="${ENV:-prod}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

case "$PROVIDER" in
  upcloud|hetzner|vultr|scaleway) ROOT_KIND=providers ;;
  # An operations root, not a VPN node provider (terraform/ops).
  egress-proxy) ROOT_KIND=ops ;;
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

TF_DIR="${REPO_ROOT}/terraform/${ROOT_KIND}/${PROVIDER}"
[[ -d "$TF_DIR" ]] || { echo "missing Terraform root: $TF_DIR" >&2; exit 2; }
[[ $# -gt 0 ]] || { echo "usage: $0 <tofu command> [args...]" >&2; exit 2; }

workspace="$ENV"
[[ "$ENV" == "prod" ]] && workspace="default"
[[ "${TF_BACKEND_ROOT:-}" == /* ]] || {
  echo "TF_BACKEND_ROOT must be the absolute directory of ${PROVIDER}.s3.tfbackend" >&2
  exit 2
}
backend_config="${TF_BACKEND_ROOT}/${PROVIDER}.s3.tfbackend"
[[ -f "$backend_config" ]] || { echo "missing backend file: $backend_config" >&2; exit 2; }
snapshot=""
if [[ "$1" == "init" ]]; then
  snapshot="$(mktemp "${TMPDIR:-/tmp}/tofu-backend.XXXXXXXX")"
  trap 'rm -f -- "$snapshot"' EXIT
fi
TF_DATA_DIR="$(python3 "${REPO_ROOT}/scripts/tofu_backend.py" "$TF_DIR" "$workspace" "$backend_config" "$snapshot")" || exit 2
export TF_DATA_DIR
export TF_VAR_plan_backend_scope="${PROVIDER}/${workspace}/${TF_DATA_DIR##*/}"

tf() {
  tofu "-chdir=${TF_DIR}" "$@"
}

if [[ "$1" == "init" ]]; then
  backend_args=("-backend-config=$snapshot")
  if [[ ! -f "${TF_DIR}/ci_backend_override.tf" ]]; then
    # The S3 backend must lock even if a backend file contains an HCL override.
    backend_args+=("-backend-config=use_lockfile=true")
  fi
  tf "$@" "${backend_args[@]}"
  if ! tf workspace select "$workspace" >/dev/null 2>&1; then
    tf workspace new "$workspace"
  fi
  exit 0
fi

if ! tf workspace select "$workspace" >/dev/null 2>&1; then
  echo "Terraform workspace '$workspace' does not exist for ${PROVIDER}/${ENV}; run 'make PROVIDER=${PROVIDER} ENV=${ENV} init' first." >&2
  exit 1
fi

# destroy.sh and the observability staging cleanup disable prevent_destroy for
# the whole provider root, so for every environment of that provider. Only the
# owner's plan and apply may run meanwhile.
if [[ "${VPN_DESTROY_OVERRIDE_OWNER:-}" != "1" ]]; then
  for override in "${TF_DIR}/_destroy_override.tf" "${TF_DIR}/_observability_cleanup_override.tf"; do
    [[ -e "$override" ]] || continue
    case "$1" in
      plan|apply|destroy)
        echo "refusing tofu $1: ${override} disables prevent_destroy for every ${PROVIDER} environment." >&2
        echo "A destroy is running or crashed. Wait for it, or confirm that no destroy runs and remove the file." >&2
        exit 1
        ;;
    esac
  done
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

exec tofu "-chdir=${TF_DIR}" "$@"
