#!/usr/bin/env bash
# Run a battery of "canary" probes that exercise distinct TSPU
# detection layers, record the per-probe verdict, and diff against
# yesterday's run. A diff means TSPU rules likely changed.
#
# Designed to run from an in-cohort RU test box on a daily cron:
#
#   27 3 * * *  cd ~/GitRep/vpn-deploy && make tspu-canary
#
# The verdicts are interesting only from inside the cohort whose
# behaviour you care about (RU mobile / RU home ISP / specific
# operator). Run from a non-RU box and you mostly see baseline
# reachability, not TSPU rule changes.
#
# Probes (each: pass / fail; "fail" = the canary endpoint did NOT
# return its expected response shape):
#   tls-no-utls   — plain TLS to a known TLS-policed endpoint
#   wg-handshake  — WireGuard 148-byte Initiation to a known WG endpoint
#   dtls12        — DTLS 1.2 ClientHello via openssl s_client -dtls1_2
#   classic-vless — vanilla VLESS+TLS (no REALITY) handshake
#   plain-https   — control: GET / over plain TLS to a baseline site
set -euo pipefail

# Portable bounded-run wrapper. macOS lacks `timeout` (coreutils ships it as
# `gtimeout`); use that, or run without a limit if neither is present. On Linux
# this resolves to `timeout`, so behaviour there is unchanged.
run_timeout() {
  local secs="$1"; shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "$secs" "$@"
  elif command -v gtimeout >/dev/null 2>&1; then
    gtimeout "$secs" "$@"
  else
    "$@"
  fi
}

STATE_DIR="${HOME}/.cache/vpn-deploy/tspu-canary"
mkdir -p "$STATE_DIR"

# Canary endpoints. Operators tune these to match the cohort they
# want to probe; defaults are public reference endpoints.
: "${CANARY_TLS_HOST:=www.example.com}"
: "${CANARY_TLS_PORT:=443}"
: "${CANARY_WG_HOST:=}"            # set to a known WG endpoint IP:port
: "${CANARY_DTLS_HOST:=}"          # set to a known DTLS endpoint host:port
: "${CANARY_VLESS_HOST:=}"         # set to a known vanilla VLESS endpoint
: "${CANARY_BASELINE_HOST:=www.cloudflare.com}"

today_file="${STATE_DIR}/$(date -u +%Y-%m-%d).tsv"
yest_file="${STATE_DIR}/$(date -u -d 'yesterday' +%Y-%m-%d 2>/dev/null || date -u -v-1d +%Y-%m-%d).tsv"
results=()

probe() {
  local name="$1" verdict="$2"
  results+=("$(printf '%s\t%s' "$name" "$verdict")")
  printf '  %-15s %s\n' "$name" "$verdict"
}

run_tls() {
  local host="$1" port="$2"
  if run_timeout 8 openssl s_client -connect "${host}:${port}" -servername "${host}" \
        -tls1_3 -alpn h2 </dev/null 2>/dev/null \
        | grep -q "BEGIN CERTIFICATE"; then
    echo pass
  else
    echo fail
  fi
}

run_dtls() {
  local host="$1" port="$2"
  if run_timeout 8 openssl s_client -connect "${host}:${port}" -dtls1_2 \
        </dev/null 2>/dev/null \
        | grep -q "BEGIN CERTIFICATE"; then
    echo pass
  else
    echo fail
  fi
}

run_baseline() {
  if curl -fsS --max-time 8 -o /dev/null "https://${CANARY_BASELINE_HOST}/cdn-cgi/trace"; then
    echo pass
  else
    echo fail
  fi
}

run_wg() {
  local hostport="$1"
  # WireGuard handshake initiation is a UDP packet with a fixed 148-byte
  # shape. We don't have a generic client at hand, so we treat the
  # endpoint as "unreachable" if a plain UDP socket can't deliver a
  # 148-byte payload. This is coarse — it's a CHANGE detector, not a
  # full handshake verifier.
  python3 - <<PY
import socket, sys
host, _, port = "$hostport".partition(":")
if not host or not port:
    sys.exit("skip")
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(3)
    s.sendto(b"\\x01\\x00\\x00\\x00" + b"\\x00" * 144, (host, int(port)))
    s.recv(2048)
    print("pass")
except socket.timeout:
    print("fail")
except Exception:
    print("fail")
PY
}

echo "TSPU canary run $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "  endpoints: tls=${CANARY_TLS_HOST}:${CANARY_TLS_PORT}"
echo "             wg=${CANARY_WG_HOST:-(unset; skipped)}"
echo "             dtls=${CANARY_DTLS_HOST:-(unset; skipped)}"
echo "             vless=${CANARY_VLESS_HOST:-(unset; skipped)}"
echo "             baseline=${CANARY_BASELINE_HOST}"
echo

probe "plain-https"  "$(run_baseline)"
probe "tls-no-utls"  "$(run_tls "$CANARY_TLS_HOST" "$CANARY_TLS_PORT")"
if [[ -n "$CANARY_DTLS_HOST" ]]; then
  probe "dtls12" "$(run_dtls "${CANARY_DTLS_HOST%%:*}" "${CANARY_DTLS_HOST##*:}")"
else
  probe "dtls12" "skip"
fi
if [[ -n "$CANARY_WG_HOST" ]]; then
  probe "wg-handshake" "$(run_wg "$CANARY_WG_HOST")"
else
  probe "wg-handshake" "skip"
fi
if [[ -n "$CANARY_VLESS_HOST" ]]; then
  probe "classic-vless" "$(run_tls "${CANARY_VLESS_HOST%%:*}" "${CANARY_VLESS_HOST##*:}")"
else
  probe "classic-vless" "skip"
fi

# Persist today's verdicts
printf '%s\n' "${results[@]}" > "$today_file"
chmod 0600 "$today_file"

echo
echo "stored: $today_file"

# Diff against yesterday
if [[ -f "$yest_file" ]]; then
  diff_out="$(diff -u "$yest_file" "$today_file" || true)"
  if [[ -n "$diff_out" ]]; then
    echo
    echo "DRIFT — verdicts changed since yesterday:"
    echo "$diff_out"
    if [[ -n "${NTFY_TOPIC:-}" ]]; then
      auth=()
      [[ -n "${NTFY_TOKEN:-}" ]] && auth=(-H "Authorization: Bearer ${NTFY_TOKEN}")
      curl -fsS -X POST \
        -H "Title: TSPU canary drift" \
        -H "Priority: high" \
        -H "Tags: warning,tspu,canary" \
        "${auth[@]}" \
        --data "$diff_out" \
        "${NTFY_URL:-https://ntfy.sh}/${NTFY_TOPIC}" >/dev/null || true
    fi
  else
    echo
    echo "no drift since yesterday"
  fi
else
  echo
  echo "no yesterday baseline yet (file: $yest_file)"
fi
