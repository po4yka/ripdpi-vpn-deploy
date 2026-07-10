#!/usr/bin/env bash
# Drift report: compare the deployed state against the last
# vpn-deploy-known-good-* tag.
#
# Workflow:
#   1. `make verify` sets a marker (--tag-on-success) so the last clean
#      deploy is identifiable by tag.
#   2. Operator runs `make drift-since-tag` weekly. The script:
#        a. finds the latest vpn-deploy-known-good-* tag
#        b. lists every commit since the tag (the intentional drift)
#        c. shows terraform plan against current tfvars
#        d. shows ansible-playbook --check --diff against the inventory
#      → output is a "what would change if I re-deployed today" report.
#
# Closes the failure class "somebody ssh'd in and edited xray config by
# hand; the next deploy will silently revert it".
#
# Flags:
#   --repo-only   Only run section [1/3] (git log). Skips terraform plan and
#                 ansible --check. Used by the scheduled CI job, which cannot
#                 decrypt SOPS secrets or reach live provider APIs (secrets
#                 outside the repo invariant). Operator-side cron uses the
#                 full mode via the install-operator-crons path.
set -euo pipefail

REPO_ONLY=false
for arg in "$@"; do
  case "$arg" in
    --repo-only) REPO_ONLY=true ;;
  esac
done

PROVIDER="${PROVIDER:-upcloud}"
ENV="${ENV:-prod}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TF_DIR="${REPO_ROOT}/terraform/providers/${PROVIDER}"

TAG="$(git -C "$REPO_ROOT" describe --tags --match 'vpn-deploy-known-good-*' --abbrev=0 2>/dev/null || true)"
if [[ -z "$TAG" ]]; then
  echo "no vpn-deploy-known-good-* tag yet; tag the current state with:"
  echo "  git tag vpn-deploy-known-good-$(date +%Y-%m-%d)"
  echo "or pass --tag-on-success to \`make verify\`."
  exit 2
fi

echo "=================================================================="
echo "Drift report — base: $TAG"
echo "=================================================================="

echo
echo "[1/3] Intentional drift (commits since the tag):"
git -C "$REPO_ROOT" --no-pager log --oneline "${TAG}..HEAD" || echo "  (none)"

if [[ "$REPO_ONLY" == "true" ]]; then
  echo
  echo "[2/3] Terraform plan: skipped (--repo-only mode; no provider credentials in CI)"
  echo "[3/3] Ansible --check: skipped (--repo-only mode; SOPS decrypt not available in CI)"
else
  echo
  echo "[2/3] Terraform plan (no apply, --refresh-only):"
  if [[ -d "$TF_DIR" ]]; then
    env PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" plan \
      -refresh-only \
      -var-file="environments/${ENV}.tfvars" \
      -no-color 2>&1 | sed 's/^/  /' || echo "  (terraform plan failed — inspect manually)"
  else
    echo "  (no terraform dir for provider=$PROVIDER)"
  fi

  echo
  echo "[3/3] Ansible --check --diff against inventory:"
  if [[ -z "${VPN_SECRETS_FILE:-}" || ! -f "$VPN_SECRETS_FILE" ]]; then
    echo "  VPN_SECRETS_FILE missing — run 'make decrypt' first to enable this section"
  else
    ansible-playbook "${REPO_ROOT}/ansible/playbooks/site.yml" \
      --check --diff 2>&1 | sed 's/^/  /' || echo "  (ansible --check failed — inspect manually)"
  fi
fi

echo
echo "=================================================================="
echo "End of drift report"
echo "=================================================================="
