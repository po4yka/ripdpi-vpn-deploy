#!/usr/bin/env bash
# Probe TLS policing behaviour on the path between the client and a target IP.
# Two distinct threshold regimes are known:
#   - Mobile/residential cohorts: >~12 concurrent TLS handshakes to a single
#     IP:443 triggers a 60-120 s silent block on that pair.
#   - Hosting-AS cohorts: the threshold can be as low as ~3 parallel
#     connections within a ~120 s window — so drops can appear at N=3 before
#     N=12 is ever reached. The low-N steps (2, 3) in the default step list
#     exist specifically to detect this tighter regime.
#
# This script opens N parallel TLS handshakes (using openssl s_client)
# and measures how many actually complete the handshake. The shape of
# the curve tells you whether the *path between this client and the
# target* policed the burst.
#
# Run from a client network you care about — NOT from the VPS itself.
# A common pattern is to ssh into a low-cost VPS inside the cohort's
# AS and run this against the production VPS.
#
# Usage:
#   scripts/test-tls-policing.sh --host vpn.example.com --port 443
#   scripts/test-tls-policing.sh --host 1.2.3.4 --steps 1,2,3,4,8,12,16,24
#
# Reports a table: N → completed / dropped / median handshake ms.
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

HOST=""
PORT=443
# Default step list includes low-N values (2, 3) to detect hosting-AS cohorts
# that trip at ~3 parallel connections within ~120 s, well before the N≈12
# threshold characteristic of mobile/residential cohorts. Override with
# --steps if you only care about one regime.
STEPS="1,2,3,4,8,12,16,24"
TIMEOUT=10
COOLDOWN=120

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)     HOST="$2"; shift 2 ;;
    --port)     PORT="$2"; shift 2 ;;
    --steps)    STEPS="$2"; shift 2 ;;
    --timeout)  TIMEOUT="$2"; shift 2 ;;
    --cooldown) COOLDOWN="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,/^set -euo/p' "$0" | sed '$d' >&2
      exit 1 ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

[[ -n "$HOST" ]] || { echo "--host required" >&2; exit 1; }
for tool in openssl python3; do
  command -v "$tool" >/dev/null 2>&1 || { echo "missing tool: $tool" >&2; exit 1; }
done

WORK="$(mktemp -d -t tls-policing.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

one_handshake() {
  local id="$1"
  local out="${WORK}/h-${id}"
  local t0 t1 ms ok=0
  t0="$(python3 -c 'import time; print(int(time.time()*1000))')"
  if run_timeout "$TIMEOUT" \
       openssl s_client -connect "${HOST}:${PORT}" -servername "$HOST" \
                        -tls1_3 -alpn h2 \
                        < /dev/null >"$out" 2>&1; then
    ok=1
  fi
  t1="$(python3 -c 'import time; print(int(time.time()*1000))')"
  ms=$(( t1 - t0 ))
  printf '%s\n' "$id,$ok,$ms" > "${WORK}/r-${id}"
}

# Sequential ramp through STEPS values, with cooldown between bursts so a
# previous burst's block window doesn't pollute the next measurement.
echo
printf '%-6s %-10s %-10s %-12s\n' N COMPLETED DROPPED P50_MS
printf '%-6s %-10s %-10s %-12s\n' --- --------- ------- ------
IFS=',' read -r -a step_list <<< "$STEPS"
for n in "${step_list[@]}"; do
  rm -f "${WORK}"/r-* "${WORK}"/h-*
  pids=()
  for i in $(seq 1 "$n"); do
    one_handshake "$i" &
    pids+=("$!")
  done
  for pid in "${pids[@]}"; do wait "$pid" || true; done

  completed=0; dropped=0; ms_list=()
  for r in "${WORK}"/r-*; do
    IFS=',' read -r _id ok ms < "$r"
    if [[ "$ok" == "1" ]]; then
      completed=$((completed+1)); ms_list+=("$ms")
    else
      dropped=$((dropped+1))
    fi
  done

  p50="-"
  if (( ${#ms_list[@]} > 0 )); then
    p50="$(printf '%s\n' "${ms_list[@]}" \
      | python3 -c "import statistics,sys; print(int(statistics.median(int(x) for x in sys.stdin.read().split())))")"
  fi

  printf '%-6s %-10s %-10s %-12s\n' "$n" "$completed" "$dropped" "$p50"

  if (( n != ${step_list[-1]} )); then
    sleep "$COOLDOWN"
  fi
done

echo
echo "Interpretation:"
echo "  * dropped rises sharply at N=2-3  → hosting-AS tight-threshold policing (~3 parallel/120s)"
echo "                                       switch this cohort to xray_flow_mode: mux"
echo "  * dropped rises sharply at N≈12   → mobile/residential cohort policing (~12 parallel/60-120s)"
echo "                                       switch this cohort to xray_flow_mode: mux"
echo "  * dropped flat across all N        → TLS policing not active for this path"
echo "  * P50 spikes >5000 ms at large N   → soft policing (rate-limit), not silent block"
