#!/usr/bin/env bash
# Credential-free policy evaluation of an already-rendered Terraform plan.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ $# -ne 1 || ! -f "$1" ]]; then
  echo "usage: check-tf-plan.sh <plan.json>" >&2
  exit 1
fi
exec python3 "${REPO_ROOT}/scripts/terraform-plan-policy.py" "$1"
