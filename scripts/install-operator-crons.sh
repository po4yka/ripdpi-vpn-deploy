#!/usr/bin/env bash
# Install the operator-side cron jobs documented in each watcher's
# header. Generates a single `vpn-deploy` cron block and writes it
# via `crontab -l | rg -v '^# vpn-deploy:' ; cat block | crontab -`
# semantics on Linux, or as a launchd plist on macOS.
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
#   daily   asn-drift                 alerts on ASN reassignment
#   daily   check-ip-reputation       Spamhaus / optional FireHOL file / AbuseIPDB
#   */2 *   watch-spare               (only when warm-spare ENV set)
#                                      uses protocol quorum when LIVENESS_CONFIG is set
#   */2 *   monitor-protocol-liveness (when LIVENESS_CONFIG is set without
#                                      a warm-spare ENV)
#   daily   tspu-canary               TSPU rule-drift probes
#   daily   probing-summary           7-day rollup
#   daily   backup-state              encrypted local TF state backup
#   daily   probe-payload-throttle    per-ASN ~16 KiB payload-throttle probe
#                                      (only when PAYLOAD_THROTTLE_HOST is set)
#   daily   monitor-reality-target    active target ASN/path signal
#                                      (only when REALITY_TARGET_VANTAGE is set)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROVIDER="${PROVIDER:-upcloud}"
ENV="${ENV:-prod}"
WARM_SPARE_ENV="${WARM_SPARE_ENV:-}"
PAYLOAD_THROTTLE_HOST="${PAYLOAD_THROTTLE_HOST:-}"
REALITY_TARGET_VANTAGE="${REALITY_TARGET_VANTAGE:-}"
LIVENESS_CONFIG="${LIVENESS_CONFIG:-}"
SOPS_FILE="${SOPS_FILE:-}"
SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-}"
OPERATOR_PATH="${OPERATOR_PATH:-}"

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

if [[ -n "$REALITY_TARGET_VANTAGE" ]]; then
  if [[ "$REALITY_TARGET_VANTAGE" == "unfiltered" ]] || ! [[ "$REALITY_TARGET_VANTAGE" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "REALITY_TARGET_VANTAGE must be a filtered technical label using letters, digits, dot, underscore, or hyphen" >&2
    exit 2
  fi
fi

MARKER_BEGIN="# vpn-deploy: BEGIN — managed block, do not edit"
MARKER_END="# vpn-deploy: END"

build_operator_path() {
  local command_name command_path directory result="" separator=""
  if [[ -n "$OPERATOR_PATH" ]]; then
    printf '%s' "$OPERATOR_PATH"
    return
  fi
  # Order is significant: the validated operator Python must precede Apple's
  # dependency-minimal /usr/bin/python3 in cron's lookup path.
  for command_name in python3 sops age terraform ansible-playbook jq make curl ssh logger openssl git gtimeout timeout whois dig host; do
    command_path="$(command -v "$command_name" 2>/dev/null || true)"
    [[ "$command_path" == /* ]] || continue
    directory="${command_path%/*}"
    case ":${result}:" in
      *":${directory}:"*) continue ;;
    esac
    result+="${separator}${directory}"
    separator=":"
  done
  for directory in /usr/local/bin /usr/bin /bin /usr/sbin /sbin; do
    case ":${result}:" in
      *":${directory}:"*) continue ;;
    esac
    result+="${separator}${directory}"
    separator=":"
  done
  printf '%s' "$result"
}

make_block() {
  local repo="$1" repo_q env_q vantage_q liveness_q sops_q age_key_q operator_path path_escaped
  printf -v repo_q '%q' "$repo"
  printf -v env_q '%q' "$ENV"
  printf -v vantage_q '%q' "$REALITY_TARGET_VANTAGE"
  printf -v sops_q '%q' "$SOPS_FILE"
  printf -v age_key_q '%q' "$SOPS_AGE_KEY_FILE"
  operator_path="$(build_operator_path)"
  [[ -n "$operator_path" && "$operator_path" != *$'\n'* && "$operator_path" != *$'\r'* ]] || {
    echo "OPERATOR_PATH must be one line" >&2
    return 1
  }
  (( ${#operator_path} <= 900 )) || {
    echo "OPERATOR_PATH exceeds the portable crontab line limit" >&2
    return 1
  }
  path_escaped="${operator_path//\\/\\\\}"
  path_escaped="${path_escaped//\"/\\\"}"
  cat <<EOF
${MARKER_BEGIN}
# Operator-side cron jobs for ${PROVIDER}:${ENV}. Re-run
# scripts/install-operator-crons.sh to refresh, --remove to uninstall.
PATH="${path_escaped}"

*/30 * * * *   cd ${repo} && PROVIDER=${PROVIDER} ENV=${ENV} make burn-check          2>&1 | logger -t vpn-burn
7 3 * * *      cd ${repo} && PROVIDER=${PROVIDER} ENV=${ENV} make asn-drift           2>&1 | logger -t vpn-asn
17 3 * * *     cd ${repo} && PROVIDER=${PROVIDER} ENV=${ENV} make check-ip-reputation 2>&1 | logger -t vpn-iprep
27 3 * * *     cd ${repo} && make tspu-canary                                         2>&1 | logger -t vpn-canary
37 3 * * *     cd ${repo} && PROVIDER=${PROVIDER} ENV=${ENV} make probing-summary     2>&1 | logger -t vpn-probing
47 3 * * *     cd ${repo} && PROVIDER=${PROVIDER} ENV=${ENV} make backup-state        2>&1 | logger -t vpn-state
EOF
  if [[ -n "$WARM_SPARE_ENV" ]]; then
    liveness_env=""
    if [[ -n "$LIVENESS_CONFIG" ]]; then
      [[ -f "$LIVENESS_CONFIG" ]] || { echo "LIVENESS_CONFIG not found: $LIVENESS_CONFIG" >&2; return 1; }
      printf -v liveness_q '%q' "$LIVENESS_CONFIG"
      liveness_env=" LIVENESS_CONFIG=${liveness_q}"
    else
      echo "warm-spare watcher will use legacy TCP-only reachability; set LIVENESS_CONFIG for protocol quorum" >&2
    fi
    cat <<EOF
*/2 * * * *    cd ${repo} && PROVIDER=${PROVIDER} ENV=${ENV} GREEN_ENV=${WARM_SPARE_ENV}${liveness_env} make watch-spare  2>&1 | logger -t vpn-spare
EOF
  elif [[ -n "$LIVENESS_CONFIG" ]]; then
    [[ -f "$LIVENESS_CONFIG" ]] || { echo "LIVENESS_CONFIG not found: $LIVENESS_CONFIG" >&2; return 1; }
    printf -v liveness_q '%q' "$LIVENESS_CONFIG"
    cat <<EOF
*/2 * * * *    cd ${repo_q} && SOPS_FILE=${sops_q} SOPS_AGE_KEY_FILE=${age_key_q} make monitor-protocol-liveness LIVENESS_CONFIG=${liveness_q}  2>&1 | logger -t vpn-liveness
EOF
  fi
  if [[ -n "$PAYLOAD_THROTTLE_HOST" ]]; then
    cat <<EOF
7 4 * * *      cd ${repo} && make probe-payload-throttle HOST=${PAYLOAD_THROTTLE_HOST} >>/tmp/vpn-payload-throttle.log 2>&1
EOF
  fi
  if [[ -n "$REALITY_TARGET_VANTAGE" ]]; then
    cat <<EOF
17 4 * * *     cd ${repo_q} && ENV=${env_q} VANTAGE=${vantage_q} make monitor-reality-target  2>&1 | logger -t vpn-reality-target
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
