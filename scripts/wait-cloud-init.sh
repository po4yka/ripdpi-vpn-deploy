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
USER="$(PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw admin_user)"
SSH_PORT="$(PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw ssh_port)"

if ! [[ "$SSH_PORT" =~ ^[1-9][0-9]*$ ]] || (( SSH_PORT > 65535 )); then
  echo "invalid ssh_port output for ${PROVIDER}:${ENV}: ${SSH_PORT}" >&2
  exit 1
fi

# Bound the SSH process itself as well as its connection and remote command.
# ConnectTimeout alone does not bound a connected but unresponsive session.
bounded_ssh() {
  python3 - "$@" <<'PYTHON'
import subprocess
import sys
try:
    result = subprocess.run(["ssh", *sys.argv[2:]], timeout=int(sys.argv[1]))
except subprocess.TimeoutExpired:
    sys.exit(124)
sys.exit(result.returncode)
PYTHON
}

echo "waiting for SSH on ${USER}@${IP}:${SSH_PORT}…"
ssh_up=""
for _ in $(seq 1 30); do
  if bounded_ssh 15 -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
         -o ConnectTimeout=5 \
         -p "$SSH_PORT" \
         -i "${ANSIBLE_SSH_PRIVATE_KEY_FILE}" \
         "${USER}@${IP}" 'true' 2>/dev/null; then
    ssh_up=1
    break
  fi
  sleep 5
done

if [[ -z "$ssh_up" ]]; then
  echo "error: SSH on ${USER}@${IP}:${SSH_PORT} did not come up after 30 bounded attempts" >&2
  exit 1
fi

echo "SSH up. Waiting for cloud-init to finish (maximum 300s)…"
status=0
bounded_ssh 320 -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
    -o ConnectTimeout=10 \
    -p "$SSH_PORT" \
    -i "${ANSIBLE_SSH_PRIVATE_KEY_FILE}" \
    "${USER}@${IP}" \
    'timeout 300 cloud-init status --wait >/dev/null 2>&1 || exit 20; test -f /var/lib/cloud-init-vpn-bootstrap.done || exit 22' || status=$?
case "$status" in
  0) echo "bootstrap ready on ${IP}" ;;
  20) echo "error: cloud-init failed or exceeded its deadline on ${IP}" >&2; exit 1 ;;
  22) echo "error: bootstrap marker is missing on ${IP}" >&2; exit 1 ;;
  *) echo "error: bootstrap SSH failed or timed out on ${IP} (status ${status})" >&2; exit 1 ;;
esac
