#!/usr/bin/env bash
# Watch the blue VPS reachability from this workstation; when it fails N
# consecutive checks, generate a one-time OTP and push an ntfy alert
# instructing the operator to run `make promote-spare OTP=<value>`.
#
# Designed to run from cron every 1-5 minutes:
#
#   */2 * * * * cd ~/GitRep/vpn-deploy && make watch-spare 2>&1 | logger -t vpn-spare
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
STATE_DIR="${VPN_SPARE_STATE_DIR:-${HOME}/.cache/vpn-deploy/spare-state}"
mkdir -p "$STATE_DIR"
chmod 0700 "$STATE_DIR"

notify_operator() {
  local title="$1" priority="$2" tags="$3" body="$4"
  if [[ -n "${NTFY_TOPIC:-}" ]]; then
    local ntfy_url="${NTFY_URL:-https://ntfy.sh}"
    local auth=()
    [[ -n "${NTFY_TOKEN:-}" ]] && auth=(-H "Authorization: Bearer ${NTFY_TOKEN}")
    curl -fsS -X POST -H "Title: ${title}" -H "Priority: ${priority}" -H "Tags: ${tags}" "${auth[@]}" --data "$body" "${ntfy_url%/}/${NTFY_TOPIC}" >/dev/null || echo "warm-spare: ntfy push failed (will retry next run)" >&2
  else
    echo "$body"
  fi
}

if [[ -n "${LIVENESS_CONFIG:-}" ]]; then
  [[ -f "$LIVENESS_CONFIG" ]] || { echo "warm-spare: liveness config not found: $LIVENESS_CONFIG" >&2; exit 1; }
  protocol_liveness="${PROTOCOL_LIVENESS:-${REPO_ROOT}/scripts/protocol-liveness.py}"
  decision_json="$("$protocol_liveness" --config "$LIVENESS_CONFIG" --state-dir "$STATE_DIR/liveness")"
  IFS=$'\t' read -r decision streak threshold otp_ttl policies < <(DECISION_JSON="$decision_json" python3 -c 'import json,os; d=json.loads(os.environ["DECISION_JSON"]); print("\t".join(map(str, [d["decision"], d["candidate_streak"], d["failure_threshold"], d["otp_ttl_seconds"], ",".join(d["candidate_policies"])])))')
  otp_file="${STATE_DIR}/pending-otp"
  context_file="${STATE_DIR}/pending-otp-context.json"
  evidence="$(DECISION_JSON="$decision_json" python3 -c 'import json,os; d=json.loads(os.environ["DECISION_JSON"]); rows=[e["sentinel"]+":"+",".join(k+"="+v for k,v in sorted(e["profiles"].items())) for e in d.get("evidence",[])]; print("; ".join(rows) or "none")')"

  if [[ "$decision" != "rotation_candidate" ]]; then
    rm -f "$otp_file" "$context_file"
    case "$decision" in
      healthy) echo "warm-spare: protocol liveness healthy" ;;
      degraded)
        notify_operator "warm-spare: protocol degraded ${PROVIDER}:${BLUE_ENV}" high "warning,vpn,protocol-degraded" "Protocol liveness is degraded but rotation quorum is not met. Evidence: ${evidence}"
        ;;
      unknown)
        errors="$(DECISION_JSON="$decision_json" python3 -c 'import json,os; print("; ".join(json.loads(os.environ["DECISION_JSON"]).get("monitoring_errors",[])) or "unspecified")')"
        notify_operator "warm-spare: liveness monitoring degraded ${PROVIDER}:${BLUE_ENV}" high "warning,vpn,monitoring-degraded" "Protocol liveness monitoring degraded; rotation is inhibited. Errors: ${errors}. Evidence: ${evidence}"
        ;;
    esac
    exit 0
  fi

  echo "warm-spare: protocol rotation candidate (streak=${streak}/${threshold})"
  if (( streak < threshold )); then
    exit 0
  fi

  now=$(date +%s)
  existing_otp=""
  existing_mtime=0
  if [[ -s "$otp_file" ]]; then
    existing_otp="$(cut -f1 "$otp_file")"
    existing_mtime="$(cut -f2 "$otp_file" 2>/dev/null || echo 0)"
  fi
  context_matches=0
  if [[ -n "$existing_otp" && -f "$context_file" ]] && (( now - existing_mtime < otp_ttl )); then
    if DECISION_JSON="$decision_json" CONTEXT_FILE="$context_file" PROVIDER_VALUE="$PROVIDER" BLUE_VALUE="$BLUE_ENV" GREEN_VALUE="$GREEN_ENV" python3 - <<'PY'
import json, os, pathlib
decision = json.loads(os.environ["DECISION_JSON"])
context = json.loads(pathlib.Path(os.environ["CONTEXT_FILE"]).read_text())
matches = (
    context.get("provider") == os.environ["PROVIDER_VALUE"]
    and context.get("blue_env") == os.environ["BLUE_VALUE"]
    and context.get("green_env") == os.environ["GREEN_VALUE"]
    and context.get("config_sha256") == decision.get("config_sha256")
    and context.get("candidate_policies") == decision.get("candidate_policies")
)
raise SystemExit(0 if matches else 1)
PY
    then
      context_matches=1
    fi
  fi
  if (( context_matches )); then
    otp="$existing_otp"
  else
    otp="$(openssl rand -hex 6)"
    printf '%s\t%s\n' "$otp" "$now" > "$otp_file"
    chmod 0600 "$otp_file"
  fi
  DECISION_JSON="$decision_json" PROVIDER_VALUE="$PROVIDER" BLUE_VALUE="$BLUE_ENV" GREEN_VALUE="$GREEN_ENV" \
    python3 - "$context_file" <<'PY'
import json, os, pathlib, sys
decision = json.loads(os.environ["DECISION_JSON"])
context = {
    "schema_version": 1,
    "provider": os.environ["PROVIDER_VALUE"],
    "blue_env": os.environ["BLUE_VALUE"],
    "green_env": os.environ["GREEN_VALUE"],
    "config_sha256": decision["config_sha256"],
    "candidate_policies": decision["candidate_policies"],
    "evaluated_at": decision.get("evaluated_at"),
    "otp_ttl_seconds": decision["otp_ttl_seconds"],
}
path = pathlib.Path(sys.argv[1])
path.write_text(json.dumps(context, sort_keys=True) + "\n")
path.chmod(0o600)
PY

  msg="Protocol liveness failed quorum for policy ${policies} during ${streak} consecutive evaluations.

To promote the warm-spare, run from the operator workstation:

  make promote-spare OTP=${otp}

The OTP is bound to this environment, policy, and liveness configuration and expires in $((otp_ttl / 60)) min."
  msg+=$'\n'"Evidence: ${evidence}"
  notify_operator "warm-spare: protocol rotation required ${PROVIDER}:${BLUE_ENV}" urgent "rotating_light,vpn,warm-spare" "$msg"
  exit 0
fi

echo "warm-spare: WARNING using legacy TCP-only reachability; set LIVENESS_CONFIG for authenticated protocol rotation signals" >&2

# Tunables
: "${FAIL_THRESHOLD:=3}"
: "${OTP_TTL_SECONDS:=3600}"     # OTP valid for one hour
: "${PROBE_TIMEOUT:=5}"

TF_DIR="${REPO_ROOT}/terraform/providers/${PROVIDER}"

blue_ip=""
if [[ -d "$TF_DIR" ]]; then
  blue_ip="$(PROVIDER="$PROVIDER" ENV="$BLUE_ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw server_ipv4 2>/dev/null || true)"
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
