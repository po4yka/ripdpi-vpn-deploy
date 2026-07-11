#!/usr/bin/env bash
# Install the operator-side cron jobs documented in each watcher's
# header. Generates a single `vpn-deploy` cron block and writes it
# via the local crontab command.
#
# Idempotent: every entry is keyed under a single # vpn-deploy marker
# block, so re-runs replace the block rather than appending duplicates.
#
# Usage:
#   PROVIDER=upcloud ENV=prod scripts/install-operator-crons.sh
#   scripts/install-operator-crons.sh --dry-run        # print plan
#   scripts/install-operator-crons.sh --remove         # uninstall
#
# What gets installed:
#   */30 *  burn-check                catches IP-burn within 30 min
#   @daily  asn-drift                 alerts on ASN reassignment
#   @daily  check-ip-reputation       Spamhaus / optional FireHOL file / AbuseIPDB
#   */2 *   watch-spare               (only when warm-spare ENV set)
#                                      uses protocol quorum when LIVENESS_CONFIG is set
#   @daily  tspu-canary               TSPU rule-drift probes
#   @daily  probing-summary           7-day rollup
#   @daily  backup-state              encrypted local TF state backup
#   @daily  probe-payload-throttle    per-ASN ~16 KiB payload-throttle probe
#                                      (only when PAYLOAD_THROTTLE_HOST is set)
#   @daily  monitor-reality-target    active target ASN/path signal
#                                      (only when REALITY_TARGET_VANTAGE is set)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROVIDER="${PROVIDER:-upcloud}"
ENV="${ENV:-prod}"
WARM_SPARE_ENV="${WARM_SPARE_ENV:-}"
PAYLOAD_THROTTLE_HOST="${PAYLOAD_THROTTLE_HOST:-}"
REALITY_TARGET_VANTAGE="${REALITY_TARGET_VANTAGE:-}"
LIVENESS_CONFIG="${LIVENESS_CONFIG:-}"

DRY_RUN=0
REMOVE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --remove)  REMOVE=1;  shift ;;
    -h|--help) sed -n '2,/^set -euo/p' "$0" | sed '$d' >&2; exit 1 ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

case "$PROVIDER" in
  upcloud|hetzner|vultr) ;;
  *) echo "unsupported PROVIDER: $PROVIDER" >&2; exit 2 ;;
esac

validate_env_name() {
  local name="$1" value="$2"
  if [[ ! "$value" =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ ]]; then
    echo "$name must contain only letters, numbers, and hyphens: $value" >&2
    exit 2
  fi
}

validate_env_name "ENV" "$ENV"
if [[ -n "$WARM_SPARE_ENV" ]]; then
  validate_env_name "WARM_SPARE_ENV" "$WARM_SPARE_ENV"
fi
if [[ -n "$PAYLOAD_THROTTLE_HOST" ]] && ! [[ "$PAYLOAD_THROTTLE_HOST" =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ || "$PAYLOAD_THROTTLE_HOST" =~ ^\[[A-Fa-f0-9:.]+\]$ ]]; then
  echo "PAYLOAD_THROTTLE_HOST must be a DNS name, IPv4 address, or bracketed IPv6 address" >&2
  exit 2
fi

if [[ -n "$REALITY_TARGET_VANTAGE" ]]; then
  if [[ "$REALITY_TARGET_VANTAGE" == "unfiltered" ]] || ! [[ "$REALITY_TARGET_VANTAGE" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "REALITY_TARGET_VANTAGE must be a filtered technical label using letters, digits, dot, underscore, or hyphen" >&2
    exit 2
  fi
fi

MARKER_BEGIN="# vpn-deploy: BEGIN — managed block, do not edit"
MARKER_END="# vpn-deploy: END"

quote_cron_value() {
  local value_q
  printf -v value_q '%q' "$1"
  # Cron parses percent before Bash parses the command, so protect percent
  # after producing the Bash-safe representation.
  printf '%s' "${value_q//%/\\%}"
}

make_block() {
  local repo="$1" repo_q provider_q env_q warm_spare_env_q payload_host_q vantage_q liveness_q liveness_env
  repo_q="$(quote_cron_value "$repo")"
  provider_q="$(quote_cron_value "$PROVIDER")"
  env_q="$(quote_cron_value "$ENV")"
  warm_spare_env_q="$(quote_cron_value "$WARM_SPARE_ENV")"
  payload_host_q="$(quote_cron_value "$PAYLOAD_THROTTLE_HOST")"
  vantage_q="$(quote_cron_value "$REALITY_TARGET_VANTAGE")"
  liveness_q="$(quote_cron_value "$LIVENESS_CONFIG")"
  cat <<EOF
${MARKER_BEGIN}
SHELL=/bin/bash
# Operator-side cron jobs for ${PROVIDER}:${ENV}. Re-run
# scripts/install-operator-crons.sh to refresh, --remove to uninstall.

*/30 * * * *   cd ${repo_q} && PROVIDER=${provider_q} ENV=${env_q} make burn-check          2>&1 | logger -t vpn-burn
@daily         cd ${repo_q} && PROVIDER=${provider_q} ENV=${env_q} make asn-drift           2>&1 | logger -t vpn-asn
@daily         cd ${repo_q} && PROVIDER=${provider_q} ENV=${env_q} make check-ip-reputation 2>&1 | logger -t vpn-iprep
@daily         cd ${repo_q} && make tspu-canary                                             2>&1 | logger -t vpn-canary
@daily         cd ${repo_q} && PROVIDER=${provider_q} ENV=${env_q} make probing-summary     2>&1 | logger -t vpn-probing
@daily         cd ${repo_q} && PROVIDER=${provider_q} ENV=${env_q} make backup-state        2>&1 | logger -t vpn-state
EOF
  if [[ -n "$WARM_SPARE_ENV" ]]; then
    liveness_env=""
    if [[ -n "$LIVENESS_CONFIG" ]]; then
      [[ -f "$LIVENESS_CONFIG" ]] || { echo "LIVENESS_CONFIG not found: $LIVENESS_CONFIG" >&2; return 1; }
      liveness_env=" LIVENESS_CONFIG=${liveness_q}"
    else
      echo "warm-spare watcher will use legacy TCP-only reachability; set LIVENESS_CONFIG for protocol quorum" >&2
    fi
    cat <<EOF
*/2 * * * *    cd ${repo_q} && PROVIDER=${provider_q} ENV=${env_q} GREEN_ENV=${warm_spare_env_q}${liveness_env} make watch-spare  2>&1 | logger -t vpn-spare
EOF
  fi
  if [[ -n "$PAYLOAD_THROTTLE_HOST" ]]; then
    cat <<EOF
@daily         cd ${repo_q} && make probe-payload-throttle HOST=${payload_host_q} >>/tmp/vpn-payload-throttle.log 2>&1
EOF
  fi
  if [[ -n "$REALITY_TARGET_VANTAGE" ]]; then
    cat <<EOF
@daily         cd ${repo_q} && ENV=${env_q} VANTAGE=${vantage_q} make monitor-reality-target  2>&1 | logger -t vpn-reality-target
EOF
  else
    echo "REALITY target monitor skipped: set REALITY_TARGET_VANTAGE to a filtered technical label" >&2
  fi
  echo "${MARKER_END}"
}

strip_block() {
  awk -v b="$MARKER_BEGIN" -v e="$MARKER_END" '
    BEGIN { skip = 0 }
    index($0, b) { skip = 1; next }
    index($0, e) { skip = 0; next }
    !skip
  '
}

if (( REMOVE )); then
  if (( DRY_RUN )); then
    echo "[dry-run] would strip vpn-deploy block from crontab"
    crontab -l 2>/dev/null | strip_block
    exit 0
  fi
  if crontab -l 2>/dev/null | grep -q "$MARKER_BEGIN"; then
    crontab -l 2>/dev/null | strip_block | crontab -
    echo "vpn-deploy cron block removed"
  else
    echo "no vpn-deploy block in crontab"
  fi
  exit 0
fi

block="$(make_block "$REPO_ROOT")"

if (( DRY_RUN )); then
  echo "[dry-run] would write the following block to crontab:"
  echo
  echo "$block"
  exit 0
fi

# Replace any existing marked block with the new one.
{
  crontab -l 2>/dev/null | strip_block
  echo "$block"
} | crontab -

echo "vpn-deploy cron block installed:"
crontab -l | sed -n "/$MARKER_BEGIN/,/$MARKER_END/p"
