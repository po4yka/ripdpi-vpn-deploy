#!/usr/bin/env bash
# Wait for cloud-init to finish on a freshly applied VPS.
set -euo pipefail

PROVIDER="${PROVIDER:-upcloud}"
ENV="${ENV:-prod}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -z "${ANSIBLE_SSH_PRIVATE_KEY_FILE:-}" ]]; then
  echo "ANSIBLE_SSH_PRIVATE_KEY_FILE is not set" >&2
  exit 1
fi

IP="$(PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw server_ipv4)"
SSH_USER="$(PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw admin_user)"
SSH_PORT="$(PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw ssh_port)"

if ! [[ "$SSH_PORT" =~ ^[1-9][0-9]*$ ]] || (( SSH_PORT > 65535 )); then
  echo "invalid ssh_port output for ${PROVIDER}:${ENV}: ${SSH_PORT}" >&2
  exit 1
fi

ssh_controller_pid=""
cleanup_wait() {
  local result=$1
  trap - EXIT INT TERM
  if [[ -n "$ssh_controller_pid" ]]; then
    kill -TERM "$ssh_controller_pid" 2>/dev/null || true
    wait "$ssh_controller_pid" 2>/dev/null || true
  fi
  exit "$result"
}
trap 'cleanup_wait "$?"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# ConnectTimeout does not bound an established session or its proxy children.
bounded_ssh() {
  python3 - "$@" <<'PYTHON' &
import os
import signal
import subprocess
import sys
import time

cancelled = 0
def interrupted(signum, _frame):
    global cancelled
    cancelled = signum

signal.signal(signal.SIGTERM, interrupted)
signal.signal(signal.SIGINT, interrupted)
try:
    child = subprocess.Popen(["ssh", *sys.argv[2:]], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
except OSError:
    sys.exit(125)
try:
    deadline = time.monotonic() + int(sys.argv[1])
    while True:
        if cancelled:
            result = 128 + cancelled
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            result = 124
            break
        try:
            result = child.wait(timeout=min(0.1, remaining))
            break
        except subprocess.TimeoutExpired:
            continue
finally:
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    child.wait()
sys.exit(result)
PYTHON
  ssh_controller_pid=$!
  local result=0
  wait "$ssh_controller_pid" || result=$?
  ssh_controller_pid=""
  return "$result"
}

echo "waiting for SSH on ${SSH_USER}@${IP}:${SSH_PORT}…"
ssh_up=""
for _ in $(seq 1 30); do
  status=0
  bounded_ssh 15 -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
         -o ConnectTimeout=5 \
         -p "$SSH_PORT" \
         -i "${ANSIBLE_SSH_PRIVATE_KEY_FILE}" \
         "${SSH_USER}@${IP}" 'true' || status=$?
  if (( status == 0 )); then
    ssh_up=1
    break
  fi
  if (( status == 124 )); then
    echo "error: SSH session timeout on ${IP}" >&2
    exit 1
  fi
  sleep 5
done

if [[ -z "$ssh_up" ]]; then
  echo "error: SSH on ${SSH_USER}@${IP}:${SSH_PORT} did not come up after 30 attempts" >&2
  exit 1
fi

echo "SSH up. Waiting for cloud-init (30 attempts, at most 10s per session)…"
remote_wait=$(cat <<'REMOTE'
timeout --kill-after=1 5 cloud-init status --wait >/dev/null 2>&1
case "$?" in
  0) test -f /var/lib/cloud-init-vpn-bootstrap.done || exit 22 ;;
  1) exit 20 ;;
  2) exit 23 ;;
  124|137) exit 21 ;;
  *) exit 24 ;;
esac
REMOTE
)
for _ in $(seq 1 30); do
  status=0
  bounded_ssh 10 -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
    -o ConnectTimeout=10 \
    -p "$SSH_PORT" \
    -i "${ANSIBLE_SSH_PRIVATE_KEY_FILE}" \
    "${SSH_USER}@${IP}" \
    "$remote_wait" || status=$?
  case "$status" in
    0) echo "bootstrap ready on ${IP}"; exit 0 ;;
    21) continue ;;
    20) echo "error: cloud-init error on ${IP}" >&2; exit 1 ;;
    23) echo "error: cloud-init recoverable error on ${IP}" >&2; exit 1 ;;
    22) echo "error: bootstrap marker missing on ${IP}" >&2; exit 1 ;;
    24) echo "error: cloud-init status unavailable on ${IP}" >&2; exit 1 ;;
    124) echo "error: SSH session timeout on ${IP}" >&2; exit 1 ;;
    *) echo "error: bootstrap SSH transport failure on ${IP}" >&2; exit 1 ;;
  esac
done
echo "error: cloud-init timeout on ${IP}: still waiting after 30 bounded attempts" >&2
cleanup_wait 1
