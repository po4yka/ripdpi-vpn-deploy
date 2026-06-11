#!/usr/bin/env bash
# Watch the blue VPS reachability from this workstation; when it fails N
# consecutive checks, generate a one-time OTP and push an ntfy alert
# instructing the operator to run `make promote-spare OTP=<value>`.
#
# Designed to run from cron every 1-5 minutes:
#
#   */2 * * * * cd ~/GitRep/vpn-deploy && make watch-spare >>/tmp/vpn-spare.log 2>&1
#
# State directory: ~/.cache/vpn-deploy/spare-state/
#   blue-failed-streak       integer
#   blue-last-seen-unixtime  integer
#   pending-otp              the active OTP, deleted after use or after
#                            $OTP_TTL_SECONDS expiry
#
# The OTP gate prevents an attacker who compromised the ntfy topic from
# silently triggering an unwanted swap — they would need both the topic
# and the operator's local workstation to consume the OTP.
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

PROVIDER="${PROVIDER:-upcloud}"
BLUE_ENV="${BLUE_ENV:-${ENV:-prod}}"
GREEN_ENV="${GREEN_ENV:-spare}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE_DIR="${HOME}/.cache/vpn-deploy/spare-state"
mkdir -p "$STATE_DIR"

# Tunables
: "${FAIL_THRESHOLD:=3}"
: "${OTP_TTL_SECONDS:=3600}"     # OTP valid for one hour
: "${PROBE_TIMEOUT:=5}"

TF_DIR="${REPO_ROOT}/terraform/providers/${PROVIDER}"

blue_ip=""
if [[ -d "$TF_DIR" ]]; then
  blue_ip="$(terraform -chdir="$TF_DIR" output -raw server_ipv4 2>/dev/null || true)"
fi
if ! [[ "$blue_ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "warm-spare: blue IP not available (provider=$PROVIDER env=$BLUE_ENV)" >&2
  exit 0
fi

streak_file="${STATE_DIR}/blue-failed-streak"
last_seen_file="${STATE_DIR}/blue-last-seen-unixtime"
otp_file="${STATE_DIR}/pending-otp"

if [[ -f "$streak_file" ]]; then
  streak="$(<"$streak_file")"
else
  streak=0
fi

if run_timeout "$PROBE_TIMEOUT" bash -c "</dev/tcp/$blue_ip/443" 2>/dev/null; then
  date +%s > "$last_seen_file"
  echo 0 > "$streak_file"
  echo "watch-spare: blue ok (${blue_ip}:443)"
  exit 0
fi

streak=$((streak + 1))
echo "$streak" > "$streak_file"
echo "watch-spare: blue failed (streak=${streak}/${FAIL_THRESHOLD})"

if (( streak < FAIL_THRESHOLD )); then
  exit 0
fi

# ---------------------------------------------------------------------------
# Failure threshold reached. Issue an OTP (or reuse an unexpired one).
# ---------------------------------------------------------------------------
now=$(date +%s)
existing_otp=""
existing_mtime=0
if [[ -s "$otp_file" ]]; then
  existing_otp="$(cut -f1 "$otp_file")"
  existing_mtime="$(cut -f2 "$otp_file" 2>/dev/null || echo 0)"
fi

if [[ -n "$existing_otp" ]] && (( now - existing_mtime < OTP_TTL_SECONDS )); then
  otp="$existing_otp"
else
  otp="$(openssl rand -hex 6)"
  printf '%s\t%s\n' "$otp" "$now" > "$otp_file"
  chmod 0600 "$otp_file"
fi

msg="Blue VPS unreachable for ${streak} probes (${blue_ip}:443).

To promote the warm-spare, run from the operator workstation:

  make promote-spare OTP=${otp}

OTP expires in $((OTP_TTL_SECONDS / 60)) min. Re-running watch-spare
keeps refreshing the OTP until consumed."

if [[ -n "${NTFY_TOPIC:-}" ]]; then
  NTFY_URL="${NTFY_URL:-https://ntfy.sh}"
  auth=()
  [[ -n "${NTFY_TOKEN:-}" ]] && auth=(-H "Authorization: Bearer ${NTFY_TOKEN}")
  curl -fsS -X POST \
    -H "Title: warm-spare: promote required ${PROVIDER}:${BLUE_ENV}" \
    -H "Priority: urgent" \
    -H "Tags: rotating_light,vpn,warm-spare" \
    "${auth[@]}" \
    --data "$msg" \
    "${NTFY_URL%/}/${NTFY_TOPIC}" >/dev/null || \
    echo "warm-spare: ntfy push failed (will retry next run)" >&2
else
  echo "$msg"
fi
