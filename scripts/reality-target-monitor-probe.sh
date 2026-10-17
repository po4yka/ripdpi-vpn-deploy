#!/usr/bin/env bash
# Monitor the configured REALITY target from an explicitly filtered vantage; observe target-path health plus ASN/prefix drift, persist only redacted technical state, and alert after repeated unhealthy observations without editing secrets, selecting a replacement, or invoking deployment actions.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV="${ENV:-prod}"
SOPS_FILE="${SOPS_FILE:-${HOME}/.config/vpn-provision/${ENV}.secrets.sops.yaml}"
VANTAGE="${VANTAGE:-}"
PROBE_TIMEOUT="${PROBE_TIMEOUT:-12}"
NTFY_URL="${NTFY_URL:-https://ntfy.sh}"
ACCEPT_BASELINE=0

usage() { echo "usage: VANTAGE=<technical-label> $0 [--accept-baseline]" >&2; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --accept-baseline) ACCEPT_BASELINE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

emit_boot_error() {
  printf '{"schema_version":1,"verdict":"error","reason_codes":["%s"],"asns":[],"prefixes":[],"observations":[],"consecutive_unhealthy":0,"alert_event":"none","alert_delivery":"not_requested","baseline_created":false,"baseline_accepted":false,"target_fingerprint":""}\n' "$1"
}

if [[ -z "$VANTAGE" || "$VANTAGE" == "unfiltered" ]]; then
  emit_boot_error "filtered_vantage_required"; exit 2
fi
if ! [[ "$VANTAGE" =~ ^[A-Za-z0-9._-]+$ ]]; then
  emit_boot_error "invalid_vantage_label"; exit 2
fi
if ! [[ "$PROBE_TIMEOUT" =~ ^[1-9][0-9]*$ ]]; then
  emit_boot_error "invalid_probe_timeout"; exit 2
fi
if [[ -z "${VPN_SECRETS_FILE:-}" && ! -f "$SOPS_FILE" ]]; then
  emit_boot_error "sops_file_missing"; exit 2
fi
if [[ -n "${VPN_SECRETS_FILE:-}" && ! -f "$VPN_SECRETS_FILE" ]]; then
  emit_boot_error "decrypted_secrets_missing"; exit 2
fi
for tool in jq python3 openssl curl; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    emit_boot_error "missing_tool"; exit 2
  fi
done
if [[ -z "${VPN_SECRETS_FILE:-}" ]] && ! command -v sops >/dev/null 2>&1; then
  emit_boot_error "missing_tool"; exit 2
fi

REALITY_VALIDATION_END="$(python3 "${REPO_ROOT}/scripts/reality_target_validation.py" deadline)" || { emit_boot_error "invalid_budget"; exit 2; }
export REALITY_VALIDATION_END

STATE_DIR="${XDG_STATE_HOME:-${HOME}/.local/state}/vpn-deploy/reality-target-monitor"
STATE_FILE="${STATE_DIR}/${ENV}.json"
mkdir -p "$STATE_DIR"
chmod 0700 "$STATE_DIR"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/reality-target-monitor.XXXXXX")"
SECRETS_TMP="${WORK}/secrets.json"
SECRETS_SOURCE="${VPN_SECRETS_FILE:-}"
OWN_SECRETS=0
cleanup() {
  if (( OWN_SECRETS )) && [[ -f "$SECRETS_TMP" ]]; then
    shred -u "$SECRETS_TMP" 2>/dev/null || rm -f "$SECRETS_TMP"
  fi
  rm -rf "$WORK"
}
trap cleanup EXIT

umask 077
if [[ -z "$SECRETS_SOURCE" ]]; then
  if ! python3 "${REPO_ROOT}/scripts/reality_target_validation.py" bounded secrets \
      sops --decrypt --output-type json --output "$SECRETS_TMP" "$SOPS_FILE"; then
    emit_boot_error "sops_decrypt_failed"; exit 2
  fi
  OWN_SECRETS=1
  SECRETS_SOURCE="$SECRETS_TMP"
fi

TARGET="$(jq -er '.xray.target' "$SECRETS_SOURCE" 2>/dev/null || true)"
SERVER_NAMES="$(jq -er '.xray.server_names[]' "$SECRETS_SOURCE" 2>/dev/null || true)"
NTFY_TOPIC="${NTFY_TOPIC:-$(jq -r '.watchdog_secrets.ntfy_topic // empty' "$SECRETS_SOURCE")}"
NTFY_TOKEN="${NTFY_TOKEN:-$(jq -r '.watchdog_secrets.ntfy_token // empty' "$SECRETS_SOURCE")}"
if [[ -z "$TARGET" || -z "$SERVER_NAMES" || "$TARGET" != *:* ]]; then
  emit_boot_error "target_config_invalid"; exit 2
fi

IPS_FILE="${WORK}/ips"
REASONS_FILE="${WORK}/reasons"
OBS_FILE="${WORK}/observations.tsv"
: > "$IPS_FILE"; : > "$REASONS_FILE"; : > "$OBS_FILE"

# Shared collector owns bounded DNS/TLS/HTTP/metadata sessions and one run budget.
# Failed/partial runs still feed the state engine, so stale health cannot survive.
export TARGET SERVER_NAMES PROBE_TIMEOUT
if ! python3 "${REPO_ROOT}/scripts/reality_target_validation.py" collect \
    --observations "$OBS_FILE" --reasons "$REASONS_FILE" --names "${WORK}/names"; then
  [[ -s "$REASONS_FILE" ]] || echo "collector_failed" >> "$REASONS_FILE"
fi

[[ ! -s "${WORK}/names" ]] || SERVER_NAMES="$(cat "${WORK}/names")"

FINAL_REPORT="${WORK}/final-report.json"
evaluate_args=(evaluate --observations "$OBS_FILE" --reasons "$REASONS_FILE" --state "$STATE_FILE" --vantage "$VANTAGE")
[[ -z "${_MONITOR_CAPTURED_AT:-}" ]] || evaluate_args+=(--captured-at "$_MONITOR_CAPTURED_AT")
(( ACCEPT_BASELINE == 0 )) || evaluate_args+=(--accept-baseline)
set +e
TARGET="$TARGET" SERVER_NAMES="$SERVER_NAMES" python3 "${REPO_ROOT}/scripts/reality_target_monitor.py" "${evaluate_args[@]}" > "$FINAL_REPORT"
state_result=$?
set -e
if [[ ! -s "$FINAL_REPORT" ]]; then
  emit_boot_error "state_engine_failed"; exit 2
fi

alert_event="$(jq -r '.alert_event' "$FINAL_REPORT")"
alert_delivery="not_requested"
delivery_result=0
if [[ "$alert_event" == "alert" || "$alert_event" == "recovery" ]]; then
  if [[ -z "$NTFY_TOPIC" ]]; then
    echo "REALITY target monitor: alert channel unavailable" >&2
    alert_delivery="failed"; delivery_result=4
  else
    if [[ "$alert_event" == "alert" ]]; then
      alert_title="REALITY target ASN/path signal ${ENV}"; alert_priority="high"; alert_tags="warning,vpn,reality-target,asn-signal"
    else
      alert_title="REALITY target ASN/path recovered ${ENV}"; alert_priority="default"; alert_tags="white_check_mark,vpn,reality-target"
    fi
    alert_body="$(jq -r '"vantage=" + .vantage + " verdict=" + .verdict + " consecutive=" + (.consecutive_unhealthy|tostring) + " asns=" + (.asns|join(",")) + " prefixes=" + (.prefixes|join(",")) + " reasons=" + (.reason_codes|join(","))' "$FINAL_REPORT")"
    auth_args=(); [[ -z "$NTFY_TOKEN" ]] || auth_args=(-H "Authorization: Bearer ${NTFY_TOKEN}")
    if python3 "${REPO_ROOT}/scripts/reality_target_validation.py" bounded alert curl -fsS --connect-timeout 5 --max-time 12 -X POST -H "Title: ${alert_title}" -H "Priority: ${alert_priority}" -H "Tags: ${alert_tags}" "${auth_args[@]}" --data "$alert_body" "${NTFY_URL%/}/${NTFY_TOPIC}" >/dev/null; then
      alert_delivery="sent"
    else
      echo "REALITY target monitor: alert delivery failed" >&2
      alert_delivery="failed"; delivery_result=4
    fi
  fi
fi

OUTPUT_REPORT="${WORK}/output-report.json"
delivery_args=(record-delivery --state "$STATE_FILE" --report "$FINAL_REPORT" --delivery "$alert_delivery")
[[ "$alert_event" == "recovery" && "$alert_delivery" == "sent" ]] && delivery_args+=(--recovery-delivered)
python3 "${REPO_ROOT}/scripts/reality_target_monitor.py" "${delivery_args[@]}" > "$OUTPUT_REPORT"
cat "$OUTPUT_REPORT"
(( state_result == 0 )) || exit "$state_result"
exit "$delivery_result"
