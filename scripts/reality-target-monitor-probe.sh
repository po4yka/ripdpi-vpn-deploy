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
if command -v timeout >/dev/null 2>&1; then
  TIMEOUT_BIN="timeout"
elif command -v gtimeout >/dev/null 2>&1; then
  TIMEOUT_BIN="gtimeout"
else
  emit_boot_error "missing_timeout_tool"; exit 2
fi

STATE_DIR="${XDG_STATE_HOME:-${HOME}/.local/state}/vpn-deploy/reality-target-monitor"
STATE_FILE="${STATE_DIR}/${ENV}.json"
mkdir -p "$STATE_DIR"
chmod 0700 "$STATE_DIR"

WORK="$(mktemp -d -t reality-target-monitor.XXXXXX)"
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
  if ! VPN_RUNTIME_DIR="$WORK" SECRETS_FILE="$SECRETS_TMP" SOPS_FILE="$SOPS_FILE" ENV="$ENV" "${REPO_ROOT}/scripts/decrypt-secrets.sh" >/dev/null; then
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
HOST="${TARGET%:*}"
PORT="${TARGET##*:}"
if ! [[ "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
  emit_boot_error "target_port_invalid"; exit 2
fi

IPS_FILE="${WORK}/ips"
REASONS_FILE="${WORK}/reasons"
OBS_FILE="${WORK}/observations.tsv"
: > "$IPS_FILE"; : > "$REASONS_FILE"; : > "$OBS_FILE"

resolve_ipv4_all() {
  local host_name="$1" out=""
  if command -v getent >/dev/null 2>&1; then
    out="$(getent ahostsv4 "$host_name" 2>/dev/null | awk '/^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/{print $1}' || true)"
  fi
  if [[ -z "$out" ]] && command -v dig >/dev/null 2>&1; then
    out="$(dig +short A "$host_name" 2>/dev/null | awk '/^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/{print}' || true)"
  fi
  if [[ -z "$out" ]] && command -v host >/dev/null 2>&1; then
    out="$(host -t A "$host_name" 2>/dev/null | awk '/has address/{print $NF}' || true)"
  fi
  if [[ -z "$out" ]]; then
    out="$(python3 - "$host_name" <<'PY' 2>/dev/null || true
import socket, sys
try:
    rows = socket.getaddrinfo(sys.argv[1], None, socket.AF_INET, socket.SOCK_STREAM)
except OSError:
    rows = []
for address in sorted({row[4][0] for row in rows}):
    print(address)
PY
)"
  fi
  printf '%s\n' "$out" | awk 'NF' | sort -u
}

san_covers() {
  local sni="$1" san_blob="$2" entry suffix label
  while IFS= read -r entry; do
    [[ -n "$entry" ]] || continue
    if [[ "$entry" == \*.* ]]; then
      suffix=".${entry#*.}"
      if [[ "$sni" == *"$suffix" ]]; then
        label="${sni%"$suffix"}"
        [[ -n "$label" && "$label" != *.* ]] && return 0
      fi
    elif [[ "$entry" == "$sni" ]]; then
      return 0
    fi
  done <<< "$san_blob"
  return 1
}

resolve_ipv4_all "$HOST" > "$IPS_FILE"
[[ -s "$IPS_FILE" ]] || echo "dns_no_ipv4" >> "$REASONS_FILE"
while IFS= read -r ip; do
  [[ -n "$ip" ]] || continue
  asn=""; prefix=""; pair_count=0; failed_pairs=0
  if asn_line="$("${REPO_ROOT}/scripts/probe-asn.sh" "$ip" 2>/dev/null)"; then
    asn="AS$(printf '%s' "$asn_line" | awk -F'\t' '{print $2}')"
    prefix="$(printf '%s' "$asn_line" | awk -F'\t' '{print $3}')"
  else
    echo "asn_lookup_failed" >> "$REASONS_FILE"
  fi
  while IFS= read -r sni; do
    [[ -n "$sni" ]] || continue
    pair_count=$((pair_count + 1)); pair_failed=0
    set +e
    tls_out="$("$TIMEOUT_BIN" "$PROBE_TIMEOUT" openssl s_client -connect "${ip}:${PORT}" -servername "$sni" -tls1_3 -alpn h2 -showcerts -verify_return_error -verify_hostname "$sni" </dev/null 2>/dev/null)"
    tls_result=$?
    set -e
    if ! printf '%s' "$tls_out" | grep -q -- '-----BEGIN CERTIFICATE-----'; then
      echo "tls_handshake_failed" >> "$REASONS_FILE"; pair_failed=1
    else
      (( tls_result == 0 )) || { echo "certificate_validation_failed" >> "$REASONS_FILE"; pair_failed=1; }
      printf '%s' "$tls_out" | grep -q 'ALPN protocol: h2' || { echo "h2_unavailable" >> "$REASONS_FILE"; pair_failed=1; }
      san_blob="$(printf '%s' "$tls_out" | openssl x509 -noout -ext subjectAltName 2>/dev/null | grep 'DNS:' | tr ',' '\n' | sed -E 's/.*DNS://; s/[[:space:]]//g' || true)"
      san_covers "$sni" "$san_blob" || { echo "certificate_san_mismatch" >> "$REASONS_FILE"; pair_failed=1; }
    fi
    http_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 --resolve "${sni}:${PORT}:${ip}" "https://${sni}:${PORT}/" 2>/dev/null || true)"
    [[ -n "$http_code" && "$http_code" != "000" ]] || { echo "https_no_response" >> "$REASONS_FILE"; pair_failed=1; }
    (( pair_failed == 0 )) || failed_pairs=$((failed_pairs + 1))
  done <<< "$SERVER_NAMES"
  printf '%s\t%s\t%s\t%s\t%s\n' "$ip" "$asn" "$prefix" "$pair_count" "$failed_pairs" >> "$OBS_FILE"
done < "$IPS_FILE"

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
    if curl -fsS -X POST -H "Title: ${alert_title}" -H "Priority: ${alert_priority}" -H "Tags: ${alert_tags}" "${auth_args[@]}" --data "$alert_body" "${NTFY_URL%/}/${NTFY_TOPIC}" >/dev/null; then
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
