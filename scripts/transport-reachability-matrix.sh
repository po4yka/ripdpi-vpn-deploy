#!/usr/bin/env bash
# Orchestrator for `.github/workflows/transport-reachability-matrix.yml`.
# Sweeps a list of transport-profile sets against an already-provisioned
# UpCloud VPS, reconfiguring the VPS between sweeps and running the
# rkn-block-checker four-layer baseline from this runner against the
# exit IP after each sweep.
#
# This runner sits on an unfiltered network. The reports it produces
# are the *non-filtered* half of the matrix — the filtered-vantage
# half is operator-driven (see docs/TRANSPORT-REACHABILITY-MATRIX.md).
#
# Required env (set by the CI workflow):
#   ENV, PROVIDER          — make / terraform / ansible state
#   SECRETS_FILE           — decrypted secrets path
#   ANSIBLE_SSH_PRIVATE_KEY_FILE
#   SKIP_PRECHECK          — must be "1" for ci-bootstrap-secrets paths
#
# Usage:
#   transport-reachability-matrix.sh --profiles "p0,p0p1,p0p1p2" \
#                                    --secrets /tmp/vpn-ci.secrets.yaml \
#                                    --output-dir .transport-reachability

set -euo pipefail

PROFILES=""
SECRETS=""
OUTPUT_DIR=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profiles)   PROFILES="$2"; shift 2 ;;
    --secrets)    SECRETS="$2"; shift 2 ;;
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

[[ -z "$PROFILES" || -z "$SECRETS" || -z "$OUTPUT_DIR" ]] && {
  echo "usage: $0 --profiles <list> --secrets <path> --output-dir <dir>" >&2
  exit 2
}

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$OUTPUT_DIR"

# ---------------------------------------------------------------------------
# Profile expansion. Each shorthand maps to a space-separated list of
# `vpn.enable_*=true|false` extra-vars. Roles that need real hardware
# (TUN, kernel modules, external network) stay off in every CI profile.
# ---------------------------------------------------------------------------
CI_BASE_VARS="vpn.enable_amneziawg=false vpn.enable_geodata=false vpn.enable_backup=false vpn.enable_monitoring=false vpn.enable_warp_outbound=false vpn.enable_honeypot=false vpn.enable_policy_ratelimit=false vpn.enable_dns_morph_bridge=false vpn.enable_hysteria_realm=false"

profile_extra_vars() {
  case "$1" in
    p0)
      echo "vpn.enable_xray_reality=true vpn.enable_nginx_xhttp=false vpn.enable_hysteria=false $CI_BASE_VARS" ;;
    p0p1)
      echo "vpn.enable_xray_reality=true vpn.enable_nginx_xhttp=true vpn.enable_hysteria=false $CI_BASE_VARS" ;;
    p0p1p2)
      echo "vpn.enable_xray_reality=true vpn.enable_nginx_xhttp=true vpn.enable_hysteria=true $CI_BASE_VARS" ;;
    p0p4)
      # P4 = dns-morph-bridge. Override the base toggle for this profile.
      echo "vpn.enable_xray_reality=true vpn.enable_nginx_xhttp=false vpn.enable_hysteria=false vpn.enable_amneziawg=false vpn.enable_geodata=false vpn.enable_backup=false vpn.enable_monitoring=false vpn.enable_warp_outbound=false vpn.enable_honeypot=false vpn.enable_policy_ratelimit=false vpn.enable_dns_morph_bridge=true vpn.enable_hysteria_realm=false" ;;
    p0p5)
      # P5 = hysteria-realm. Same approach.
      echo "vpn.enable_xray_reality=true vpn.enable_nginx_xhttp=false vpn.enable_hysteria=false vpn.enable_amneziawg=false vpn.enable_geodata=false vpn.enable_backup=false vpn.enable_monitoring=false vpn.enable_warp_outbound=false vpn.enable_honeypot=false vpn.enable_policy_ratelimit=false vpn.enable_dns_morph_bridge=false vpn.enable_hysteria_realm=true" ;;
    *)
      echo "" ;;
  esac
}

# ---------------------------------------------------------------------------
# Resolve the exit IP once — it does not change across profile sweeps.
# ---------------------------------------------------------------------------
EXIT_IP="$(terraform -chdir="${REPO_ROOT}/terraform/providers/${PROVIDER}" output -raw server_ipv4)"
[[ -n "$EXIT_IP" ]] || { echo "could not resolve server_ipv4 from terraform" >&2; exit 1; }
echo "exit-ip: $EXIT_IP"

# ---------------------------------------------------------------------------
# SNI-variant survival baseline. For each REALITY server_name, probe both the
# bare and the www.-prefixed SNI against the exit IP and record which survives
# (KB: sni-exact-match-vs-suffix-classification-2026). This runner is the
# *unfiltered* vantage, so every variant is expected to survive here — that is
# the hygiene baseline. The decision-grade measurement is the operator's
# filtered (RU) vantage: `EXIT_IP=$EXIT_IP VANTAGE=filtered make probe-sni-survival`.
# The exit IP / Reality identity are constant across profiles, so this is
# probed once, not per profile. Non-fatal.
# ---------------------------------------------------------------------------
"${REPO_ROOT}/scripts/probe-sni-survival.sh" "$EXIT_IP" \
  --secrets "$SECRETS" \
  --vantage "${VANTAGE:-unfiltered}" \
  --out "${OUTPUT_DIR}/sni-survival.json" \
  || echo "::warning::SNI-variant survival probe failed (non-fatal)"

# Top-level index gets appended to as profiles complete.
INDEX="${OUTPUT_DIR}/index.json"
echo '{"schema_version": 1, "vantage": "unfiltered", "exit_ip": "'"$EXIT_IP"'", "sni_survival_report": "sni-survival.json", "profiles": {}}' > "$INDEX"

IFS=',' read -r -a profile_list <<< "$PROFILES"
for profile in "${profile_list[@]}"; do
  profile="$(echo "$profile" | tr -d '[:space:]')"
  [[ -z "$profile" ]] && continue

  extra="$(profile_extra_vars "$profile")"
  if [[ -z "$extra" ]]; then
    echo "::warning::unknown profile shorthand '$profile' — skipping"
    continue
  fi

  echo "=================================================="
  echo "profile: $profile"
  echo "extra-vars: $extra"
  echo "=================================================="

  VPN_SECRETS_FILE="$SECRETS" ansible-playbook "${REPO_ROOT}/ansible/playbooks/site.yml" \
    --extra-vars "$extra"

  profile_dir="${OUTPUT_DIR}/${profile}"
  mkdir -p "$profile_dir"

  # Run the rkn-block-checker baseline; the wrapper exits non-zero when
  # verdicts shifted vs a previous run — first run produces no diff and
  # exits zero. Either way, the JSON report lands in the state-dir.
  "${REPO_ROOT}/scripts/run-rkn-block-checker.sh" \
    "$EXIT_IP" \
    --state-dir "$profile_dir" || true

  # Record the profile's extra-vars + report path in the top-level index.
  python3 - "$INDEX" "$profile" "$extra" "$profile_dir/${EXIT_IP}/latest.json" <<'PY'
import json
import pathlib
import sys

idx_path = pathlib.Path(sys.argv[1])
profile = sys.argv[2]
extra = sys.argv[3]
report_path = sys.argv[4]

idx = json.loads(idx_path.read_text())
idx["profiles"][profile] = {
    "extra_vars": extra,
    "report_path_relative": str(pathlib.Path(report_path).relative_to(idx_path.parent)),
}
idx_path.write_text(json.dumps(idx, indent=2))
PY

done

echo "transport-reachability-matrix: $(jq '.profiles | keys | length' "$INDEX") profile(s) recorded under $OUTPUT_DIR"
