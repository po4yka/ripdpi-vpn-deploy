#!/usr/bin/env bash
# Consume the pending OTP from warm-spare-watcher and run blue-green.sh
# to swing traffic from BLUE_ENV to GREEN_ENV. Refuses if no OTP is
# pending, if the supplied OTP doesn't match, or if the OTP has expired.
#
# Usage:
#   make promote-spare OTP=<value>
#
# This is the operator's confirm step. The OTP gate prevents an
# attacker who compromised the ntfy topic from triggering a swap on
# their own — they would need both the topic and a way onto this
# workstation.
set -euo pipefail

PROVIDER="${PROVIDER:-upcloud}"
BLUE_ENV="${BLUE_ENV:-${ENV:-prod}}"
GREEN_ENV="${GREEN_ENV:-spare}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE_DIR="${VPN_SPARE_STATE_DIR:-${HOME}/.cache/vpn-deploy/spare-state}"
otp_file="${STATE_DIR}/pending-otp"
context_file="${STATE_DIR}/pending-otp-context.json"
: "${OTP_TTL_SECONDS:=3600}"

given="${OTP:-${1:-}}"
[[ -n "$given" ]] || { echo "usage: $0 <OTP>   (or: make promote-spare OTP=<OTP>)" >&2; exit 1; }

if [[ ! -s "$otp_file" ]]; then
  echo "no pending OTP. warm-spare-watcher hasn't issued one." >&2
  exit 1
fi

stored="$(cut -f1 "$otp_file")"
mtime="$(cut -f2 "$otp_file")"
if [[ -f "$context_file" ]]; then
  OTP_TTL_SECONDS="$(CONTEXT_FILE="$context_file" python3 -c 'import json,os,pathlib; print(json.loads(pathlib.Path(os.environ["CONTEXT_FILE"]).read_text()).get("otp_ttl_seconds", 3600))')"
fi
now=$(date +%s)
age=$(( now - mtime ))

if (( age > OTP_TTL_SECONDS )); then
  echo "OTP expired (${age}s old; TTL ${OTP_TTL_SECONDS}s). Re-run watch-spare to issue a new one." >&2
  rm -f "$otp_file"
  exit 1
fi

if [[ "$given" != "$stored" ]]; then
  echo "OTP does not match." >&2
  exit 1
fi

if [[ -f "$context_file" ]]; then
  [[ -n "${LIVENESS_CONFIG:-}" && -f "$LIVENESS_CONFIG" ]] || {
    echo "pending OTP is protocol-bound but LIVENESS_CONFIG is unavailable" >&2
    rm -f "$otp_file" "$context_file"
    exit 1
  }
  protocol_liveness="${PROTOCOL_LIVENESS:-${REPO_ROOT}/scripts/protocol-liveness.py}"
  current="$("$protocol_liveness" --config "$LIVENESS_CONFIG")"
  if ! CURRENT_JSON="$current" CONTEXT_FILE="$context_file" PROVIDER_VALUE="$PROVIDER" BLUE_VALUE="$BLUE_ENV" GREEN_VALUE="$GREEN_ENV" python3 - <<'PY'
import json, os, pathlib
current = json.loads(os.environ["CURRENT_JSON"])
context = json.loads(pathlib.Path(os.environ["CONTEXT_FILE"]).read_text())
valid = (
    current.get("decision") == "rotation_candidate"
    and current.get("config_sha256") == context.get("config_sha256")
    and current.get("candidate_policies") == context.get("candidate_policies")
    and context.get("provider") == os.environ["PROVIDER_VALUE"]
    and context.get("blue_env") == os.environ["BLUE_VALUE"]
    and context.get("green_env") == os.environ["GREEN_VALUE"]
)
raise SystemExit(0 if valid else 1)
PY
  then
    echo "protocol liveness is no longer a rotation candidate or its binding changed" >&2
    rm -f "$otp_file" "$context_file"
    exit 1
  fi
fi

# OTP is valid — consume it immediately so it can't be replayed.
rm -f "$otp_file" "$context_file"

echo "OTP accepted. Running blue-green.sh ${PROVIDER}:${BLUE_ENV} → ${GREEN_ENV}…"
PROVIDER="$PROVIDER" BLUE_ENV="$BLUE_ENV" GREEN_ENV="$GREEN_ENV" \
  "${BLUE_GREEN_SCRIPT:-${REPO_ROOT}/scripts/blue-green.sh}"
