#!/usr/bin/env bash
# Export the selected instance's device profile. Recovery keys stay encrypted.
set -euo pipefail
[[ $# == 1 ]] || { echo 'usage: emit-awg.sh <name>' >&2; exit 2; }
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
deploy_env="${ENV:-prod}"
provider="${PROVIDER:-upcloud}"
sops_file="${SOPS_FILE:-${HOME}/.config/vpn-provision/${deploy_env}.secrets.sops.yaml}"
server_ip="$(PROVIDER="$provider" ENV="$deploy_env" "${repo_root}/scripts/terraform-env.sh" output -raw server_ipv4)"
output_args=()
[[ -z "${OUTPUT:-}" ]] || output_args+=(--output "$OUTPUT")
sops --decrypt --output-type json "$sops_file" 2>/dev/null | \
  python3 "${repo_root}/scripts/awg_client.py" config --host "${provider}:${deploy_env}" --endpoint "$server_ip" "${output_args[@]}" -- "$1"
