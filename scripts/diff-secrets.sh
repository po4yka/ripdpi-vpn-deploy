#!/usr/bin/env bash
# Read-only comparison of canonical Xray configuration, services and versions.
# Missing inputs, drift and transport/render errors all fail closed.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROVIDER="${PROVIDER:-upcloud}"
ENV="${ENV:-prod}"
if [[ -z "${ANSIBLE_SSH_PRIVATE_KEY_FILE:-}" ]]; then
  echo "ANSIBLE_SSH_PRIVATE_KEY_FILE is not set" >&2
  exit 1
fi
if [[ -z "${SECRETS_FILE:-}" || ! -f "$SECRETS_FILE" ]]; then
  echo "SECRETS_FILE missing — run 'make decrypt' first" >&2
  exit 1
fi
# Reject malformed YAML through the redacted validator before Ansible loads it.
python3 "$REPO_ROOT/scripts/validate-secrets.py" "$SECRETS_FILE" >/dev/null
host="${ANSIBLE_LIMIT:-}"
if [[ -z "$host" ]]; then
  host="$(PROVIDER="$PROVIDER" ENV="$ENV" "$REPO_ROOT/scripts/terraform-env.sh" output -raw server_hostname)"
fi
[[ "$host" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || {
  echo 'diff-secrets requires one exact inventory alias' >&2
  exit 1
}
export ANSIBLE_CONFIG="$REPO_ROOT/ansible/ansible.cfg"
export ANSIBLE_HOST_KEY_CHECKING=True
export VPN_SECRETS_FILE="$SECRETS_FILE"
# Ansible otherwise exits successfully when a misspelled limit selects no hosts.
ansible-inventory --list | python3 -c '
import json, sys
inventory = json.load(sys.stdin)
seen = set()
def members(group):
    if group in seen:
        return set()
    seen.add(group)
    entry = inventory.get(group, {})
    hosts = set(entry.get("hosts", []))
    for child in entry.get("children", []):
        hosts.update(members(child))
    return hosts
if sys.argv[1] not in members("vpn"):
    sys.exit("diff-secrets target is absent from the VPN inventory")
' "$host"
# Ansible uses the inventory SSH port and its pinned transport settings.
exec ansible-playbook "$REPO_ROOT/ansible/playbooks/diff-secrets.yml" --limit "$host"
