#!/usr/bin/env bash
# Append-only audit log for credential lifecycle events. Each event is
# an age-encrypted, ASCII-armored envelope appended to the operator's
# log file. Read side decrypts every envelope and prints JSON one
# record per line.
#
# Storage:
#   ~/.config/vpn-provision/audit.log.age  (mode 0600)
#
# Record schema:
#   {"ts": <unix>, "iso": "YYYY-MM-DDTHH:MM:SSZ",
#    "actor": "<whoami>@<host>", "action": "<verb>",
#    "client": "<name>", "env": "<env>", "provider": "<prov>",
#    "note": "<free-form>"}
#
# Writers:
#   scripts/audit-log.sh append --action issue-bootstrap \
#                               --client phone --note "OTP=..."
#   scripts/audit-log.sh append-best-effort --action new-client \
#                                           --client phone
#   make audit-log-append ACTION=… CLIENT=… [NOTE=…]
#
# Reader:
#   scripts/audit-log.sh read           # prints JSONL of every event
#   make audit-log                      # equivalent
#
# Hooks: issue-bootstrap.sh, issue-sub-token.sh, new-client.sh,
# rotate-secrets.sh, rotate-credentials, fleet-rotate, and the deploy
# wrapper append best-effort records. These hooks never fail the
# lifecycle command if local audit logging is unavailable.
set -euo pipefail

CONFIG_DIR="${HOME}/.config/vpn-provision"
AGE_KEY="${AGE_KEY:-${CONFIG_DIR}/age.key}"
LOG_FILE="${AUDIT_LOG_FILE:-${CONFIG_DIR}/audit.log.age}"

cmd="${1:-}"; [[ -n "$cmd" ]] || { echo "usage: $0 append|append-best-effort|read [args]" >&2; exit 1; }
shift || true

require() {
  command -v "$1" >/dev/null 2>&1 || { echo "missing tool: $1" >&2; exit 2; }
}

ensure_config_dir() {
  mkdir -p "$CONFIG_DIR" && chmod 0700 "$CONFIG_DIR"
}

parse_append_args() {
  ACTION=""; CLIENT=""; ENVL="${ENV:-prod}"; PROVIDER="${PROVIDER:-upcloud}"; NOTE=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --action|--client|--env|--provider|--note)
        [[ $# -ge 2 ]] || { echo "$1 requires a value" >&2; return 1; }
        case "$1" in
          --action)   ACTION="$2" ;;
          --client)   CLIENT="$2" ;;
          --env)      ENVL="$2" ;;
          --provider) PROVIDER="$2" ;;
          --note)     NOTE="$2" ;;
        esac
        shift 2
        ;;
      *) echo "unknown arg: $1" >&2; return 1 ;;
    esac
  done
  [[ -n "$ACTION" ]] || { echo "--action required" >&2; return 1; }
}

append_record() {
  ensure_config_dir || return 2
  require age
  require date
  require python3

  if [[ ! -f "$AGE_KEY" ]]; then
    echo "missing age key at $AGE_KEY — operator workstation not bootstrapped" >&2
    return 2
  fi
  recipient="$(grep -m1 '^# public key:' "$AGE_KEY" | awk '{print $4}')"
  [[ -n "$recipient" ]] || { echo "could not parse age recipient from $AGE_KEY" >&2; return 2; }

  actor="${AUDIT_ACTOR:-$(whoami)@$(hostname -s)}"
  ts="$(date -u +%s)"
  iso="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  record="$(python3 - "$ts" "$iso" "$actor" "$ACTION" "$CLIENT" "$ENVL" "$PROVIDER" "$NOTE" <<'PY'
import json
import sys

ts, iso, actor, action, client, env, provider, note = sys.argv[1:]
print(json.dumps({
  "ts": int(ts), "iso": iso, "actor": actor,
  "action": action, "client": client or None,
  "env": env, "provider": provider,
  "note": note or None,
}, sort_keys=True))
PY
)"
  {
    printf '%s\n' "$record" | age -a -r "$recipient"
  } | append_locked
  chmod 0600 "$LOG_FILE"
  echo "audit: ${ACTION} ${CLIENT:-<no-client>} → ${LOG_FILE}"
}

# Serialize envelope appends: two writers (cron watcher + interactive deploy
# wrapper) can fire around rotation events, and interleaved ciphertext would
# be silently dropped by the read path. flock on Linux, lockf on macOS — same
# fallback pattern as scripts/new-client.sh.
append_locked() {
  exec 9>> "${LOG_FILE}.lock"
  local lock_command
  if command -v flock >/dev/null 2>&1; then
    lock_command=(flock 9)
  elif command -v lockf >/dev/null 2>&1; then
    lock_command=(lockf -s -t 60 9)
  else
    echo "error: audit-log requires flock (Linux) or lockf (macOS)" >&2
    return 2
  fi
  if ! "${lock_command[@]}"; then
    echo "error: could not acquire audit log lock for $LOG_FILE" >&2
    return 2
  fi
  cat >> "$LOG_FILE"
  exec 9>&-
}

case "$cmd" in

  append)
    parse_append_args "$@" || exit 1
    append_record
    ;;

  append-best-effort)
    if ! parse_append_args "$@"; then
      echo "(warn) audit-log append skipped; invalid arguments" >&2
      exit 0
    fi
    if ! command -v age >/dev/null 2>&1 || [[ ! -f "$AGE_KEY" ]]; then
      [[ "${AUDIT_LOG_DEBUG:-0}" == "1" ]] && \
        echo "(warn) audit-log append skipped; age or key unavailable" >&2
      exit 0
    fi
    append_record || echo "(warn) audit-log append failed; continuing" >&2
    ;;

  read)
    require age
    if [[ ! -f "$LOG_FILE" ]]; then
      echo "no audit log yet at ${LOG_FILE}" >&2
      exit 0
    fi
    [[ -f "$AGE_KEY" ]] || { echo "missing age key at $AGE_KEY" >&2; exit 2; }
    python3 - "$LOG_FILE" "$AGE_KEY" <<'PY'
import pathlib, re, subprocess, sys
log = pathlib.Path(sys.argv[1]).read_text()
key = sys.argv[2]
envelopes = re.findall(
    r"-----BEGIN AGE ENCRYPTED FILE-----.*?-----END AGE ENCRYPTED FILE-----\n?",
    log, flags=re.S,
)
for env in envelopes:
    r = subprocess.run(["age", "-d", "-i", key], input=env.encode(),
                       capture_output=True)
    if r.returncode != 0:
        print(f"# decrypt failed: {r.stderr.decode().strip()}", file=sys.stderr)
        continue
    sys.stdout.write(r.stdout.decode())
PY
    ;;

  *)
    echo "unknown subcommand: $cmd  (expected: append | append-best-effort | read)" >&2
    exit 1
    ;;
esac
