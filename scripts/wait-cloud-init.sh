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

echo "waiting for SSH on ${USER}@${IP}…"
for _ in $(seq 1 30); do
  if ssh -o StrictHostKeyChecking=accept-new \
         -o ConnectTimeout=5 \
         -i "${ANSIBLE_SSH_PRIVATE_KEY_FILE}" \
         "${USER}@${IP}" 'true' 2>/dev/null; then
    break
  fi
  sleep 5
done

echo "SSH up. Waiting for cloud-init to finish…"
ssh -o StrictHostKeyChecking=accept-new \
    -i "${ANSIBLE_SSH_PRIVATE_KEY_FILE}" \
    "${USER}@${IP}" \
    'cloud-init status --wait || true; test -f /var/lib/cloud-init-vpn-bootstrap.done && echo "bootstrap marker present"'
