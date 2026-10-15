#!/usr/bin/env bash
# Issue the selected device across profiles in one locked encrypted transaction.
set -euo pipefail
emit_uri=0
if [[ "${1:-}" == "--emit-uri" ]]; then
  emit_uri=1
  shift
fi
[[ $# == 1 ]] || { echo 'usage: new-client.sh [--emit-uri] <name>' >&2; exit 2; }
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
deploy_env="${ENV:-prod}"
provider="${PROVIDER:-upcloud}"
sops_file="${SOPS_FILE:-${HOME}/.config/vpn-provision/${deploy_env}.secrets.sops.yaml}"
uri_args=()
if [[ "$emit_uri" == 1 ]]; then
  [[ -n "${OUTPUT:-}" ]] || { echo "OUTPUT=<new private recipient file> required with --emit-uri" >&2; exit 2; }
  uri_args+=(--emit-uri --output "$OUTPUT")
fi
python3 "${repo_root}/scripts/awg_client.py" enroll --host "${provider}:${deploy_env}" \
  --file "$sops_file" --all-profiles "${uri_args[@]}" -- "$1"
ENV="$deploy_env" PROVIDER="$provider" "${repo_root}/scripts/audit-log.sh" append-best-effort \
  --action new-client --client "$1" --note "emit_uri=${emit_uri}"
