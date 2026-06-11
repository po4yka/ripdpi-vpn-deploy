#!/usr/bin/env bash
# Detect ASN drift on the deployed VPS public IP. Designed to run from
# the operator workstation on a cron / launchd cadence (weekly is
# enough — providers don't reshuffle prefixes faster than that).
#
# Flow:
#   1. Read the current public IP from terraform output (or $IP).
#   2. Look up its ASN via scripts/probe-asn.sh.
#   3. Compare against the last known value stored at $STATE_FILE.
#   4. On change, push an alert via ntfy.sh using the same channel the
#      VPS-side watchdog uses, so on-call doesn't have to learn a new
#      pager surface.
#
# Why this exists: an "Avoid" tier ASN can become someone's neighbour
# overnight (provider IP reassignment). docs/PROVIDER-NOTES.md lists
# the bucket; this script makes the drift observable.
#
# Usage:
#   PROVIDER=upcloud ENV=prod scripts/asn-drift.sh
#   IP=1.2.3.4 NTFY_TOPIC=… scripts/asn-drift.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE_DIR="${HOME}/.cache/vpn-deploy"
mkdir -p "$STATE_DIR"

PROVIDER="${PROVIDER:-upcloud}"
ENV="${ENV:-prod}"
STATE_FILE="${STATE_DIR}/asn-${PROVIDER}-${ENV}.state"

if [[ -z "${IP:-}" ]]; then
  TF_DIR="${REPO_ROOT}/terraform/providers/${PROVIDER}"
  IP="$(terraform -chdir="$TF_DIR" output -raw server_ipv4 2>/dev/null || true)"
fi
if [[ -z "${IP:-}" ]]; then
  echo "no IP available (terraform output missing? export IP=… to override)" >&2
  exit 2
fi

new_line="$("${REPO_ROOT}/scripts/probe-asn.sh" "$IP")"
# format: IP \t ASN \t PREFIX \t COUNTRY \t ORG
new_asn="$(printf '%s' "$new_line" | awk -F'\t' '{print $2}')"
new_org="$(printf '%s' "$new_line" | awk -F'\t' '{print $5}')"

old_asn=""
if [[ -f "$STATE_FILE" ]]; then
  old_asn="$(awk -F'\t' '{print $2}' "$STATE_FILE")"
fi

# ASN tier blocklist (must mirror validate-reality-target.sh step 8).
AVOID_ASNS=(13335 16276 24940 14061 26383 216071)

in_avoid_tier() {
  local asn="$1"
  local bad
  for bad in "${AVOID_ASNS[@]}"; do
    [[ "$asn" == "$bad" ]] && return 0
  done
  return 1
}

send_alert() {
  local msg="$1"
  local title="$2"
  echo "$msg"
  if [[ -n "${NTFY_URL:-${NTFY_TOPIC:-}}" ]]; then
    NTFY_URL="${NTFY_URL:-https://ntfy.sh}"
    if [[ -n "${NTFY_TOPIC:-}" ]]; then
      auth=()
      [[ -n "${NTFY_TOKEN:-}" ]] && auth=(-H "Authorization: Bearer ${NTFY_TOKEN}")
      curl -fsS -X POST \
        -H "Title: ${title}" \
        -H "Priority: high" \
        -H "Tags: warning,vpn,asn-drift" \
        "${auth[@]}" \
        --data "$msg" \
        "${NTFY_URL%/}/${NTFY_TOPIC}" >/dev/null || true
    fi
  fi
}

if [[ -z "$old_asn" ]]; then
  echo "first run: recording AS${new_asn} (${new_org})"
  if in_avoid_tier "$new_asn"; then
    echo "WARNING: AS${new_asn} is in the Avoid tier — review docs/PROVIDER-NOTES.md" >&2
  fi
elif [[ "$old_asn" != "$new_asn" ]]; then
  msg="ASN drift on ${PROVIDER}:${ENV} IP=${IP}
old=AS${old_asn} → new=AS${new_asn} (${new_org})
Review docs/PROVIDER-NOTES.md tier table and rotate if Avoid."
  send_alert "$msg" "ASN drift ${PROVIDER}:${ENV}"
elif in_avoid_tier "$new_asn"; then
  msg="ASN Avoid-tier on ${PROVIDER}:${ENV} IP=${IP}
AS${new_asn} (${new_org}) is in the Avoid tier (no number change).
Review docs/PROVIDER-NOTES.md tier table and rotate."
  send_alert "$msg" "ASN Avoid-tier ${PROVIDER}:${ENV}"
else
  echo "no drift: AS${new_asn} (${new_org})"
fi

printf '%s\n' "$new_line" > "$STATE_FILE"
chmod 0600 "$STATE_FILE"
