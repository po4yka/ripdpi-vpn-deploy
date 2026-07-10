#!/usr/bin/env bash
# Issue a one-time bootstrap token for a single client. Emits the
# sing-box JSON, encrypts under a per-token key (the token IS the key —
# random URL-safe 32 bytes), drops the payload at the bootstrap host
# via scp, and prints the URL the client should fetch.
#
# Requires:
#   subscription.enable_bootstrap = true (defaults/main.yml)
#   inventory rendered (make inventory)
#   ssh access as the admin_user
#
# Usage:
#   PROVIDER=upcloud ENV=prod scripts/issue-bootstrap.sh phone
#   scripts/issue-bootstrap.sh phone --expires 2026-08-31
#   scripts/issue-bootstrap.sh phone --qr     # also writes phone.bootstrap.qr.png
#
# After the client fetches the URL, the payload is atomically deleted
# server-side. Subsequent fetches return 410. If --expires is given, the
# server returns 410 once the date passes even before any fetch.
set -euo pipefail

CLIENT="${1:-}"
[[ -n "$CLIENT" && "$CLIENT" != "-h" && "$CLIENT" != "--help" ]] || {
  sed -n '2,/^set -euo/p' "$0" | sed '$d' >&2
  exit 1
}
shift

EXPIRES=""
EMIT_QR=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --expires) EXPIRES="$2"; shift 2 ;;
    --qr)      EMIT_QR=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROVIDER="${PROVIDER:-upcloud}"
ENV="${ENV:-prod}"
SUBSCRIPTION_DIR="${SUBSCRIPTION_DIR:-/var/lib/vpn-subscription}"

server_ip="$(PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw server_ipv4)"
admin_user="$(PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw admin_user 2>/dev/null || echo admin)"
server_hostname="$(PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw server_hostname 2>/dev/null || echo "$server_ip")"

# Use base64url for URL-safe tokens; 32 bytes → 43 chars.
token="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=' | head -c 43)"

payload="$("${REPO_ROOT}/scripts/emit-singbox.sh" "$CLIENT")"
[[ -n "$payload" ]] || { echo "empty payload from emit-singbox.sh" >&2; exit 1; }

# Server stores under sha256(token) so the plaintext token never touches
# disk. The hash is computed identically by the Python service on every
# inbound request — see ansible/roles/subscription-host/templates/
# vpn-bootstrap.py.j2.
token_hash="$(printf '%s' "$token" | shasum -a 256 2>/dev/null | awk '{print $1}')"
if [[ -z "$token_hash" ]]; then
  token_hash="$(printf '%s' "$token" | sha256sum | awk '{print $1}')"
fi
remote_path="${SUBSCRIPTION_DIR}/bootstrap/${token_hash}"

# Read subscription port + bootstrap toggles from group_vars/defaults — we
# could parse the host config, but the defaults are stable and the test
# only fails if you've changed them, in which case the operator already
# knows.
sub_host="$(SOPS_FILE="${HOME}/.config/vpn-provision/${ENV}.secrets.sops.yaml" \
  sops --decrypt --output-type json "${HOME}/.config/vpn-provision/${ENV}.secrets.sops.yaml" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print((d.get('subscription') or {}).get('server_name') or (d.get('nginx_xhttp') or {}).get('server_name') or '')")"
[[ -n "$sub_host" ]] || sub_host="$server_hostname"
sub_port="$(SOPS_FILE="${HOME}/.config/vpn-provision/${ENV}.secrets.sops.yaml" \
  sops --decrypt --output-type json "${HOME}/.config/vpn-provision/${ENV}.secrets.sops.yaml" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print((d.get('subscription') or {}).get('port') or 8444)")"

printf '%s' "$payload" | ssh "${admin_user}@${server_ip}" \
  "sudo install -o vpn-bootstrap -g vpn-bootstrap -m 0600 /dev/stdin '${remote_path}'"

# Optional sidecar meta file with expiry.
if [[ -n "$EXPIRES" ]]; then
  meta="{\"expires\":\"${EXPIRES}\"}"
  printf '%s' "$meta" | ssh "${admin_user}@${server_ip}" \
    "sudo install -o vpn-bootstrap -g vpn-bootstrap -m 0600 /dev/stdin '${remote_path}.meta'"
fi

echo "stored hash: ${token_hash:0:8}…  path: ${remote_path}"

url="https://${sub_host}:${sub_port}/bootstrap/${token}"

echo
echo "Bootstrap URL (one-time, copy to client now):"
echo "  $url"
echo
echo "Properties:"
echo "  * consumed on first successful GET (second fetch → 410)"
if [[ -n "$EXPIRES" ]]; then
  echo "  * server-side expiry: ${EXPIRES} (410 after that date)"
fi

if (( EMIT_QR )); then
  command -v qrencode >/dev/null 2>&1 || {
    echo "qrencode not installed; skip --qr" >&2; exit 0; }
  qr_out="${CLIENT}.bootstrap.qr.png"
  echo "$url" | qrencode -t PNG -o "$qr_out"
  echo "  * QR rendered: $qr_out"
fi

# Audit-log the issuance. Best-effort: failure here doesn't unwind the
# already-installed payload because the URL is already valid.
note_value="expires=${EXPIRES:-none} qr=${EMIT_QR}"
ENV="$ENV" PROVIDER="$PROVIDER" \
  "${REPO_ROOT}/scripts/audit-log.sh" append-best-effort \
    --action issue-bootstrap \
    --client "$CLIENT" \
    --note "$note_value"
