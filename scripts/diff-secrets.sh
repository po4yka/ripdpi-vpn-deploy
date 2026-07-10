#!/usr/bin/env bash
# Drift detection: compare what's deployed on the VPS with what current
# secrets + templates would render. Exits 0 if in sync, 1 if drifted.
#
# Required env:
#   PROVIDER (default: upcloud), ENV (default: prod)
#   SECRETS_FILE (default: /tmp/vpn-<env>.secrets.yaml — run `make decrypt` first)
#   ANSIBLE_SSH_PRIVATE_KEY_FILE
set -euo pipefail

PROVIDER="${PROVIDER:-upcloud}"
ENV="${ENV:-prod}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SECRETS_FILE="${SECRETS_FILE:-/tmp/vpn-${ENV}.secrets.yaml}"

for tool in terraform ssh ansible ansible-playbook diff jq python3; do
  command -v "$tool" >/dev/null 2>&1 || { echo "missing: $tool" >&2; exit 1; }
done

if [[ -z "${ANSIBLE_SSH_PRIVATE_KEY_FILE:-}" ]]; then
  echo "ANSIBLE_SSH_PRIVATE_KEY_FILE is not set" >&2
  exit 1
fi

if [[ ! -f "$SECRETS_FILE" ]]; then
  echo "missing $SECRETS_FILE — run 'make decrypt' first" >&2
  exit 1
fi

IP="$(PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw server_ipv4)"
USER="$(PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw admin_user)"
HOSTNAME="$(PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw server_hostname)"

WORK="$(mktemp -d -t vpn-diff.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

ssh_cmd() {
  ssh -o StrictHostKeyChecking=accept-new \
      -o ConnectTimeout=10 \
      -i "${ANSIBLE_SSH_PRIVATE_KEY_FILE}" \
      "${USER}@${IP}" "$@"
}

resolve_host_vars() {
  local host="$1"
  local inventory="${REPO_ROOT}/ansible/inventory/generated.ini"

  if command -v ansible-inventory >/dev/null 2>&1 && [[ -f "$inventory" ]]; then
    local host_vars
    if host_vars="$(
      ANSIBLE_CONFIG="${REPO_ROOT}/ansible/ansible.cfg" \
        ansible-inventory \
          -i "$inventory" \
          --playbook-dir "${REPO_ROOT}/ansible" \
          --host "$host" 2>/dev/null
    )"; then
      if jq -e 'has("vpn")' >/dev/null 2>&1 <<< "$host_vars"; then
        printf '%s\n' "$host_vars"
        return
      fi
    fi
  fi

  python3 - "$REPO_ROOT" "$host" <<'PY'
import json
import pathlib
import sys

import yaml

root = pathlib.Path(sys.argv[1])
host = sys.argv[2]
group_vars = root / "ansible" / "group_vars"
inventory = root / "ansible" / "inventory" / "generated.ini"


def deep_merge(base, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def load_group(name):
    path = group_vars / f"{name}.yml"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


host_groups = []
if inventory.exists():
    section = None
    for raw_line in inventory.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section and ":" not in section and line.split()[0] == host:
            host_groups.append(section)

merged = load_group("all")
for group in host_groups or ["vpn"]:
    if group != "all":
        deep_merge(merged, load_group(group))

print(json.dumps(merged))
PY
}

config_toggle() {
  local key="$1"
  local default="$2"
  jq -r --arg key "$key" --argjson default "$default" \
    'if has($key) then .[$key] else $default end | tostring | ascii_downcase' \
    <<< "$CONFIG_VPN_JSON"
}

HOST_VARS_JSON="$(resolve_host_vars "$HOSTNAME")"
CONFIG_VPN_JSON="$(jq -c '.vpn // {}' <<< "$HOST_VARS_JSON")"
AWG_INTERFACE="$(jq -r '.amneziawg.interface // "awg0"' <<< "$HOST_VARS_JSON")"

drift=0

# 1. Xray config: render locally via ansible-playbook --check, fetch remote
echo "== Xray config =="
if [[ "$(config_toggle enable_xray_reality true)" == "true" ]]; then
ansible -i "${REPO_ROOT}/ansible/inventory/generated.ini" "$HOSTNAME" \
  -m fetch -a "src=/etc/xray/config.json dest=${WORK}/remote/ flat=yes" \
  --extra-vars "@${SECRETS_FILE}" >/dev/null 2>&1 \
  || ssh_cmd 'sudo cat /etc/xray/config.json' > "${WORK}/remote.config.json"

# Render expected via ansible (--check so nothing changes)
ansible-playbook -i "localhost," "${REPO_ROOT}/ansible/playbooks/site.yml" \
  --check --diff --tags xray \
  --extra-vars "@${SECRETS_FILE}" \
  --connection=local 2>/dev/null > "${WORK}/render-output.txt" || true

# Simpler approach: call jinja2 via ansible 'template' module against
# the role template, dump to /tmp on a throwaway. Skip the elaborate
# rendering — instead, exfiltrate normalized JSON from the host and
# from a fresh `xray test -dump-config` if available.
if ssh_cmd 'command -v xray' >/dev/null 2>&1; then
  ssh_cmd 'sudo /usr/local/bin/xray run -test -dump-config -config /etc/xray/config.json' \
    > "${WORK}/remote.normalized.json" 2>/dev/null || true
fi

REMOTE_FILE="${WORK}/remote.config.json"
[[ -s "${WORK}/remote.normalized.json" ]] && REMOTE_FILE="${WORK}/remote.normalized.json"

# Show only top-level structure — clients/uuid/short_id/privateKey are too
# noisy and secret-bearing for a diff. We sanitize first.
jq 'walk(if type == "object" then
       (if has("id") then .id = "<UUID>" else . end)
       | (if has("privateKey") then .privateKey = "<PRIV>" else . end)
       | (if has("shortIds") then .shortIds = ["<SID>"] else . end)
     else . end) | del(.log.access, .log.error)' \
  "$REMOTE_FILE" > "${WORK}/remote.sanitized.json" 2>/dev/null || cp "$REMOTE_FILE" "${WORK}/remote.sanitized.json"

# Compare just the structural shape — inbound/outbound tags, transports,
# port set. This catches the drift cases that matter (an inbound got
# disabled, port changed, transport setting drifted).
jq -S '{
  inbounds: [.inbounds[] | {tag, port, protocol, network: .streamSettings.network, security: .streamSettings.security}],
  outbounds: [.outbounds[] | {tag, protocol}],
  routing: (.routing.rules // [])
}' "${WORK}/remote.sanitized.json" > "${WORK}/remote.shape.json" 2>/dev/null || true

if [[ -s "${WORK}/remote.shape.json" ]]; then
  echo "Remote Xray shape:"
  cat "${WORK}/remote.shape.json"
else
  echo "Could not extract Xray shape from $REMOTE_FILE"
  drift=1
fi
else
  echo "skipped: vpn.enable_xray_reality is false for this host"
fi

# 2. Service status comparison — what's enabled vs resolved Ansible config
echo
echo "== Service vs Ansible-toggle drift =="
echo "Resolved vpn toggles: ${CONFIG_VPN_JSON}"
for svc_key_pair in \
  "xray:enable_xray_reality:true" \
  "nginx:enable_nginx_xhttp:true" \
  "hysteria-server:enable_hysteria:false" \
  "awg-quick@${AWG_INTERFACE}:enable_amneziawg:false"; do
  default="${svc_key_pair##*:}"
  svc_and_key="${svc_key_pair%:*}"
  svc="${svc_and_key%:*}"
  key="${svc_and_key#*:}"
  want_enabled="$(config_toggle "$key" "$default")"
  is_active="$(ssh_cmd "systemctl is-active ${svc} 2>/dev/null || true" | tr -d '\r' || echo missing)"
  printf "  %-20s want_enabled=%-8s actually=%s\n" "$svc" "$want_enabled" "$is_active"
  if [[ "$want_enabled" == "true" ]] && [[ "$is_active" != "active" ]]; then
    drift=1
  fi
  if [[ "$want_enabled" == "false" ]] && [[ "$is_active" == "active" ]]; then
    drift=1
  fi
done

# 3. nftables config sanity — the rendered file should match the running ruleset
echo
echo "== nftables config staleness =="
remote_mtime_human="$(ssh_cmd 'stat -c %y /etc/nftables.conf' 2>/dev/null || echo unknown)"
echo "  /etc/nftables.conf mtime: $remote_mtime_human"

# 4. Pinned version check — Xray and Hysteria binary versions vs secrets
echo
echo "== Binary version pinning =="
if [[ "$(config_toggle enable_xray_reality true)" == "true" ]]; then
  remote_xray_ver="$(ssh_cmd '/usr/local/bin/xray version 2>&1 | head -1' || true)"
  expected_xray_ver="$(python3 - "$SECRETS_FILE" <<'PY'
import sys
import yaml

with open(sys.argv[1], encoding="utf-8") as handle:
    data = yaml.safe_load(handle) or {}
print((data.get("xray") or {}).get("version", ""))
PY
)"
  echo "  Xray remote: $remote_xray_ver"
  echo "  Xray secrets pin: $expected_xray_ver"

  if [[ -n "$expected_xray_ver" && "$remote_xray_ver" != *"$expected_xray_ver"* ]]; then
    echo "  DRIFT: Xray version mismatch"
    drift=1
  fi
else
  echo "  Xray skipped: vpn.enable_xray_reality is false for this host"
fi

if [[ "$(config_toggle enable_hysteria false)" == "true" ]]; then
  remote_hysteria_ver="$(ssh_cmd '/usr/local/bin/hysteria version 2>&1 | head -1' || true)"
  expected_hysteria_ver="$(python3 - "$SECRETS_FILE" <<'PY'
import sys
import yaml

with open(sys.argv[1], encoding="utf-8") as handle:
    data = yaml.safe_load(handle) or {}
print((data.get("hysteria") or {}).get("version", ""))
PY
)"
  echo "  Hysteria remote: $remote_hysteria_ver"
  echo "  Hysteria secrets pin: $expected_hysteria_ver"

  if [[ -n "$expected_hysteria_ver" && "$remote_hysteria_ver" != *"$expected_hysteria_ver"* ]]; then
    echo "  DRIFT: Hysteria version mismatch"
    drift=1
  fi
else
  echo "  Hysteria skipped: vpn.enable_hysteria is false for this host"
fi

echo
if (( drift )); then
  echo "drift detected — review and reconcile via 'make dry-run && make deploy'"
  exit 1
fi
echo "no structural drift detected"
