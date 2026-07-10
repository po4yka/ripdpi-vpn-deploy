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
SOPS_FILE="$(SOPS_FILE="$SOPS_FILE" python3 -c 'import os; print(os.path.realpath(os.environ["SOPS_FILE"]))')"

if [[ ! -f "$SOPS_FILE" ]]; then
  echo "missing $SOPS_FILE" >&2
  exit 1
fi

umask 077
SOPS_TEMP=""
SOPS_LOCK="${SOPS_FILE}.new-client.lock"
cleanup_new_client() {
  if [[ -n "$SOPS_TEMP" ]]; then
    rm -f -- "$SOPS_TEMP"
  fi
}
trap cleanup_new_client EXIT
exec 9> "$SOPS_LOCK"
if command -v flock >/dev/null 2>&1; then
  lock_command=(flock -n 9)
elif command -v lockf >/dev/null 2>&1; then
  lock_command=(lockf -s -t 0 9)
else
  echo "error: new-client requires flock (Linux) or lockf (macOS)" >&2
  exit 1
fi
if ! "${lock_command[@]}"; then
  echo "error: another new-client transaction is active for $SOPS_FILE" >&2
  exit 1
fi

# Fail fast if a client with this name already exists in any profile and return the current array length as the insertion index for the staged transaction.
client_state() {
  local extract="$1"
  sops --decrypt --extract "$extract" --output-type json "$SOPS_FILE" 2>/dev/null |
    CLIENT_NAME="$NAME" python3 -c '
import json
import os
import sys

clients = json.load(sys.stdin)
if not isinstance(clients, list):
    raise SystemExit("client collection is not an array")
exists = any(isinstance(client, dict) and client.get("name") == os.environ["CLIENT_NAME"] for client in clients)
print(exists, len(clients))
' 2>/dev/null
}
if ! xray_state="$(client_state '["xray"]["clients"]')" ||
   ! hy_state="$(client_state '["hysteria"]["clients"]')" ||
   ! awg_state="$(client_state '["amneziawg_secrets"]["peers"]')"; then
  echo "error: failed to read client collections from $SOPS_FILE" >&2
  exit 1
fi
read -r existing_xray xray_index <<< "$xray_state"
read -r existing_hy hy_index <<< "$hy_state"
read -r existing_awg awg_index <<< "$awg_state"
if [[ "$existing_xray" == "True" || "$existing_hy" == "True" || "$existing_awg" == "True" ]]; then
  echo "error: client '${NAME}' already exists in secrets (xray=${existing_xray} hysteria=${existing_hy} awg=${existing_awg})" >&2
  echo "To replace a client, remove the existing entries first, then re-run." >&2
  exit 1
fi

if ! snell_variants_json="$(sops --decrypt --output-type json "$SOPS_FILE" 2>/dev/null | python3 -c '
import json, sys
document = json.load(sys.stdin)
json.dump((document.get("snell_secrets") or {}).get("variants") or [], sys.stdout)
')"; then
  echo "error: failed to inspect optional Snell client collections" >&2
  exit 1
fi
snell_plan="$(printf '%s' "$snell_variants_json" | CLIENT_NAME="$NAME" python3 -c '
import json, os, sys
variants = json.load(sys.stdin)
if not isinstance(variants, list):
    raise SystemExit("snell variants collection is not an array")
for index, variant in enumerate(variants):
    users = variant.get("users") or []
    variant_id = variant.get("id", index)
    if any(isinstance(user, dict) and user.get("name") == os.environ["CLIENT_NAME"] for user in users):
        raise SystemExit(f"client already exists in Snell variant {variant_id}")
    print(index, len(users), variant_id, sep="\t")
')" || { echo "error: failed to inspect Snell client collections" >&2; exit 1; }

UUID="$(uuidgen)"
SHORT_ID="$(openssl rand -hex 4)"
HY_PASSWORD="$(openssl rand -base64 24)"
AWG_PRIV="$(awg genkey 2>/dev/null || wg genkey)"
AWG_PUB="$(echo "$AWG_PRIV" | awg pubkey 2>/dev/null || echo "$AWG_PRIV" | wg pubkey)"
AWG_PSK="$(awg genpsk 2>/dev/null || wg genpsk)"
AWG_ALLOWED_IPS="$(
  sops --decrypt --extract '["amneziawg_secrets"]["peers"]' --output-type json "$SOPS_FILE" 2>/dev/null \
    | python3 -c '
import json
import re
import sys

peers = json.load(sys.stdin)
if not isinstance(peers, list):
    raise SystemExit("AmneziaWG peers collection is not an array")

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

# Apply every profile update to an encrypted sibling copy; the final rename is atomic because the staging file lives on the same filesystem as SOPS_FILE.
SOPS_TEMP="$(SOPS_FILE="$SOPS_FILE" python3 -c '
import os
import pathlib
import tempfile

path = os.path.abspath(os.environ["SOPS_FILE"])
suffix = pathlib.Path(path).suffix or ".yaml"
fd, temporary = tempfile.mkstemp(prefix=f".{os.path.basename(path)}.new-client.", suffix=suffix, dir=os.path.dirname(path))
os.close(fd)
print(temporary)
')"
cp "$SOPS_FILE" "$SOPS_TEMP"
chmod 0600 "$SOPS_TEMP"

printf '{"name":"%s","uuid":"%s","short_id":"%s"}' "$NAME" "$UUID" "$SHORT_ID" |
  sops set --value-stdin "$SOPS_TEMP" "[\"xray\"][\"clients\"][${xray_index}]"

printf '{"name":"%s","password":"%s"}' "$NAME" "$HY_PASSWORD" |
  sops set --value-stdin "$SOPS_TEMP" "[\"hysteria\"][\"clients\"][${hy_index}]"

printf '{"name":"%s","public_key":"%s","preshared_key":"%s","allowed_ips":"%s"}' "$NAME" "$AWG_PUB" "$AWG_PSK" "$AWG_ALLOWED_IPS" |
  sops set --value-stdin "$SOPS_TEMP" "[\"amneziawg_secrets\"][\"peers\"][${awg_index}]"

while IFS=$'\t' read -r variant_index user_index _variant_id; do
  [[ -n "$variant_index" ]] || continue
  SNELL_USERKEY="$(openssl rand -base64 24)"
  printf '{"name":"%s","userkey":"%s"}' "$NAME" "$SNELL_USERKEY" |
    sops set --value-stdin "$SOPS_TEMP" "[\"snell_secrets\"][\"variants\"][${variant_index}][\"users\"][${user_index}]"
done <<< "$snell_plan"

mv -f -- "$SOPS_TEMP" "$SOPS_FILE"
SOPS_TEMP=""

cat <<EOF
created client: ${NAME}
  xray UUID:        ${UUID}
  xray shortId:     ${SHORT_ID}
  hysteria pass:    (stored)
  AWG public key:   ${AWG_PUB}
  AWG allowed IPs:  ${AWG_ALLOWED_IPS}
  Snell userkeys:   $([[ -n "$snell_plan" ]] && echo "stored per variant" || echo "skipped (not configured)")

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
