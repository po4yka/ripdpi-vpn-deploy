#!/usr/bin/env bash
# One isolated transport-profile deployment and its explicitly scoped evidence.
# CI provisions a fresh node per profile; never toggle profiles on an old guest.
# Required: ENV, PROVIDER, TAILNET_HANDOFFS and canonical deployment proof inputs.
set -euo pipefail
PROFILE=""
SECRETS=""
OUTPUT_DIR=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="$2"; shift 2 ;;
    --secrets) SECRETS="$2"; shift 2 ;;
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
case "$PROFILE" in p0|p0p1|p0p1p2|p0p4|p0p5) ;; *)
  echo 'one supported --profile is required' >&2; exit 2 ;;
esac
[[ -f "$SECRETS" && -n "$OUTPUT_DIR" ]] || {
  echo 'usage: transport-reachability-matrix.sh --profile PROFILE --secrets FILE --output-dir NEW-DIR' >&2
  exit 2
}
: "${PROVIDER:?PROVIDER required}"
: "${ENV:?ENV required}"
: "${TAILNET_HANDOFFS:?TAILNET_HANDOFFS required}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Existing evidence must never masquerade as this run after a failed probe.
mkdir -p "$(dirname "$OUTPUT_DIR")"
mkdir "$OUTPUT_DIR"
HOST_ALIAS="$(PROVIDER="$PROVIDER" ENV="$ENV" "$REPO_ROOT/scripts/terraform-env.sh" output -raw server_hostname)"
[[ "$HOST_ALIAS" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || exit 1
EXIT_IP="$(PROVIDER="$PROVIDER" ENV="$ENV" "$REPO_ROOT/scripts/terraform-env.sh" output -raw server_ipv4)"
python3 - "$EXIT_IP" <<'PYIP'
import ipaddress, sys
ipaddress.IPv4Address(sys.argv[1])
PYIP
HOSTS="${PROVIDER}:${ENV}" COHORTS="ci-${PROFILE}" \
  "$REPO_ROOT/scripts/render-inventory.sh"
SECRETS_FILE="$SECRETS" ANSIBLE_LIMIT="$HOST_ALIAS" \
  make -C "$REPO_ROOT" deploy verify smoke-test

"$REPO_ROOT/scripts/probe-sni-survival.sh" "$EXIT_IP" \
  --secrets "$SECRETS" --vantage "${VANTAGE:-unfiltered}" \
  --out "$OUTPUT_DIR/sni-survival.json"
# This is a direct runner baseline, not a proxy or transport-path measurement.
"$REPO_ROOT/scripts/run-rkn-block-checker.sh" "$EXIT_IP" \
  --state-dir "$OUTPUT_DIR/runner-baseline"
python3 - "$OUTPUT_DIR" "$PROFILE" "$EXIT_IP" <<'PYREPORT'
import json
from pathlib import Path
import sys
root, profile, address = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
reports = {
    'sni_survival': root / 'sni-survival.json',
    'runner_direct_baseline': root / 'runner-baseline' / address / 'latest.json',
}
for path in reports.values():
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or not value:
        sys.exit('probe report is empty or malformed')
index = {
    'schema_version': 2, 'profile': profile, 'cohort': 'ci-' + profile,
    'exit_ip': address, 'server_verify_and_smoke': 'passed',
    'transport_client_acceptance': 'not_measured',
    'reports': {name: str(path.relative_to(root)) for name, path in reports.items()},
}
(root / 'index.json').write_text(json.dumps(index, indent=2) + '\n')
PYREPORT
