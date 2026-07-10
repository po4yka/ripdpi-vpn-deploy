#!/usr/bin/env bash
# Generate a new per-device client across all enabled profiles and append to
# the SOPS-encrypted secrets file. Optionally emit a shareable URI / payload.
#
# Usage:
#   scripts/new-client.sh <name>              # add new client to all profiles
#   scripts/new-client.sh --emit-uri <name>   # also print vless:// + hysteria2:// URIs
#
# Requires: sops, age, jq, python3, uuidgen, openssl, and awg or wg.
set -euo pipefail

EMIT_URI=0
if [[ "${1:-}" == "--emit-uri" ]]; then
  EMIT_URI=1
  shift
fi

NAME="${1:-}"
if [[ -z "$NAME" ]]; then
  echo "usage: $0 [--emit-uri] <name>" >&2
  exit 1
fi
if ! [[ "$NAME" =~ ^[A-Za-z0-9_-]{1,64}$ ]]; then
  echo "client name must contain only letters, digits, underscores, or dashes" >&2
  exit 1
fi

ENV="${ENV:-prod}"
PROVIDER="${PROVIDER:-upcloud}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOPS_FILE="${SOPS_FILE:-${HOME}/.config/vpn-provision/${ENV}.secrets.sops.yaml}"

if [[ ! -f "$SOPS_FILE" ]]; then
  echo "missing $SOPS_FILE" >&2
  exit 1
fi

# Fail fast if a client with this name already exists in any profile.
has_client() {
  local extract="$1"
  sops --decrypt --extract "$extract" --output-type json "$SOPS_FILE" 2>/dev/null |
    CLIENT_NAME="$NAME" python3 -c 'import json, os, sys; peers = json.load(sys.stdin); print(any(p.get("name") == os.environ["CLIENT_NAME"] for p in (peers or [])))' 2>/dev/null || echo False
}
existing_xray="$(has_client '["xray"]["clients"]')"
existing_hy="$(has_client '["hysteria"]["clients"]')"
existing_awg="$(has_client '["amneziawg_secrets"]["peers"]')"
if [[ "$existing_xray" == "True" || "$existing_hy" == "True" || "$existing_awg" == "True" ]]; then
  echo "error: client '${NAME}' already exists in secrets (xray=${existing_xray} hysteria=${existing_hy} awg=${existing_awg})" >&2
  echo "To replace a client, remove the existing entries first, then re-run." >&2
  exit 1
fi

UUID="$(uuidgen)"
SHORT_ID="$(openssl rand -hex 4)"
HY_PASSWORD="$(openssl rand -base64 24)"
AWG_PRIV="$(awg genkey 2>/dev/null || wg genkey)"
AWG_PUB="$(echo "$AWG_PRIV" | awg pubkey 2>/dev/null || echo "$AWG_PRIV" | wg pubkey)"
AWG_PSK="$(awg genpsk 2>/dev/null || wg genpsk)"
AWG_ALLOWED_IPS="$(
  { sops --decrypt --extract '["amneziawg_secrets"]["peers"]' --output-type json "$SOPS_FILE" 2>/dev/null || printf '[]'; } \
    | python3 -c '
import json
import re
import sys

try:
    peers = json.load(sys.stdin)
except json.JSONDecodeError:
    peers = []
if not isinstance(peers, list):
    peers = []

used = {1}
for index, peer in enumerate(peers, start=1):
    if not isinstance(peer, dict):
        continue
    allowed = str(peer.get("allowed_ips") or "").strip()
    match = re.search(r"(?:^|,\s*)10\.66\.66\.(\d+)/32(?:\s*,|$)", allowed)
    if match:
        used.add(int(match.group(1)))
    else:
        used.add(index + 1)

for octet in range(2, 255):
    if octet not in used:
        print(f"10.66.66.{octet}/32")
        break
else:
    raise SystemExit("no available AmneziaWG peer address in 10.66.66.0/24")
'
)"

# Edit secrets in place. SOPS preserves encryption boundaries when called via
# `sops set` (yaml mode).
sops set "$SOPS_FILE" \
  "[\"xray\"][\"clients\"][?(@.name == '${NAME}')]" \
  "{\"name\":\"${NAME}\",\"uuid\":\"${UUID}\",\"short_id\":\"${SHORT_ID}\"}" 2>/dev/null \
  || sops --set "[\"xray\"][\"clients\"] += [{\"name\":\"${NAME}\",\"uuid\":\"${UUID}\",\"short_id\":\"${SHORT_ID}\"}]" "$SOPS_FILE"

sops --set "[\"hysteria\"][\"clients\"] += [{\"name\":\"${NAME}\",\"password\":\"${HY_PASSWORD}\"}]" "$SOPS_FILE"

sops --set "[\"amneziawg_secrets\"][\"peers\"] += [{\"name\":\"${NAME}\",\"public_key\":\"${AWG_PUB}\",\"preshared_key\":\"${AWG_PSK}\",\"allowed_ips\":\"${AWG_ALLOWED_IPS}\"}]" "$SOPS_FILE"

cat <<EOF
created client: ${NAME}
  xray UUID:        ${UUID}
  xray shortId:     ${SHORT_ID}
  hysteria pass:    (stored)
  AWG public key:   ${AWG_PUB}
  AWG allowed IPs:  ${AWG_ALLOWED_IPS}

The client also needs the AWG private key to configure the device:
  AWG private:      ${AWG_PRIV}

Hand the private key to the device through a secure channel (Signal, in-person
QR, encrypted notes app). Do NOT email it. Do NOT store it after the device is
configured — re-issue means rotate, not recover.

To remove this client later: sops --set '...' to delete the matching entries
in xray.clients / hysteria.clients / amneziawg_secrets.peers and run
  make rotate-credentials.
EOF

ENV="$ENV" PROVIDER="$PROVIDER" \
  "${REPO_ROOT}/scripts/audit-log.sh" append-best-effort \
    --action new-client \
    --client "$NAME" \
    --note "emit_uri=${EMIT_URI} awg_allowed_ips=${AWG_ALLOWED_IPS}"

if [[ "$EMIT_URI" == "1" ]]; then
  echo
  echo "URIs (server-side fields filled from secrets; verify against your prod.tfvars):"
  echo "  vless://${UUID}@<SERVER_IP>:443?type=raw&security=reality&flow=xtls-rprx-vision&sni=<SNI>&pbk=<REALITY_PUBLIC_KEY>&sid=${SHORT_ID}#${NAME}"
  echo "  hysteria2://${NAME}:${HY_PASSWORD}@<SERVER_IP>:443/?sni=<SERVER_HOSTNAME>#${NAME}"
fi
