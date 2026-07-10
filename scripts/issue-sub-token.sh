#!/usr/bin/env bash
# Issue a long-lived /sub/<token> URL for a client. Hashed storage,
# optional per-token expiry, optional QR.
#
# Difference from issue-bootstrap.sh:
#   * /sub/ payload is NOT consumed on read — the same URL keeps
#     working until the operator either revokes the hash or the
#     sidecar `expires` date passes.
#   * Multi-host / multi-cohort sing-box bundles are typical for
#     /sub/ — operators can refresh the payload by re-running this
#     script with the same token (token printed at the bottom).
#
# Usage:
#   make issue-sub-token CLIENT=phone
#   scripts/issue-sub-token.sh phone --expires 2026-12-31 --qr
#   scripts/issue-sub-token.sh phone --refresh-token <existing-token>
#   scripts/issue-sub-token.sh phone --print-token-only   # emit bare token on stdout only
#
# The token IS the bearer. Distribute the URL over a secure channel.
set -euo pipefail

CLIENT="${1:-}"
[[ -n "$CLIENT" && "$CLIENT" != "-h" && "$CLIENT" != "--help" ]] || {
  sed -n '2,/^set -euo/p' "$0" | sed '$d' >&2
  exit 1
}
[[ "$CLIENT" =~ ^[A-Za-z0-9_-]{1,64}$ ]] || { echo "client name must contain only letters, digits, underscores, or dashes" >&2; exit 1; }
shift

EXPIRES=""
EMIT_QR=0
REFRESH_TOKEN=""
PRINT_TOKEN_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --expires)          EXPIRES="$2"; shift 2 ;;
    --qr)               EMIT_QR=1; shift ;;
    --refresh-token)    REFRESH_TOKEN="$2"; shift 2 ;;
    --print-token-only) PRINT_TOKEN_ONLY=1; shift ;;
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

if [[ -n "$REFRESH_TOKEN" ]]; then
  token="$REFRESH_TOKEN"
else
  token="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=' | head -c 43)"
fi
token_hash="$(printf '%s' "$token" | shasum -a 256 2>/dev/null | awk '{print $1}')"
if [[ -z "$token_hash" ]]; then
  token_hash="$(printf '%s' "$token" | sha256sum | awk '{print $1}')"
fi

payload="$("${REPO_ROOT}/scripts/emit-singbox.sh" "$CLIENT")"
[[ -n "$payload" ]] || { echo "empty payload from emit-singbox.sh" >&2; exit 1; }

remote_path="${SUBSCRIPTION_DIR}/sub/${token_hash}"

printf '%s' "$payload" | ssh "${admin_user}@${server_ip}" \
  "sudo install -o vpn-bootstrap -g vpn-bootstrap -m 0600 /dev/stdin '${remote_path}'"

if [[ -n "$EXPIRES" ]]; then
  meta="{\"expires\":\"${EXPIRES}\",\"client\":\"${CLIENT}\"}"
  printf '%s' "$meta" | ssh "${admin_user}@${server_ip}" \
    "sudo install -o vpn-bootstrap -g vpn-bootstrap -m 0600 /dev/stdin '${remote_path}.meta'"
fi

# Pull subscription host name + port from secrets so the URL goes to
# the subscription endpoint, not the transport one.
sops_file="${HOME}/.config/vpn-provision/${ENV}.secrets.sops.yaml"
sub_host="$(sops --decrypt --output-type json "$sops_file" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print((d.get('subscription') or {}).get('server_name') or (d.get('nginx_xhttp') or {}).get('server_name') or '')")"
[[ -n "$sub_host" ]] || sub_host="$server_hostname"
sub_port="$(sops --decrypt --output-type json "$sops_file" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print((d.get('subscription') or {}).get('port') or 8444)")"

url="https://${sub_host}:${sub_port}/sub/${token}"

if (( PRINT_TOKEN_ONLY )); then
  printf '%s\n' "$token"
  exit 0
fi

echo
echo "Subscription URL (long-lived, refresh-able):"
echo "  $url"
echo
echo "Properties:"
echo "  * stored hash: ${token_hash:0:8}…"
echo "  * hashed-on-disk; plaintext token never touches the server filesystem"
echo "  * survives multiple fetches until ${EXPIRES:-revoked}"
if [[ -n "$EXPIRES" ]]; then
  echo "  * server returns 410 after ${EXPIRES}"
fi
echo "  * revoke: append the hash to subscription.revoked_token_hashes,"
echo "    re-deploy. The Python service re-reads the file on each request."
echo

if (( EMIT_QR )); then
  command -v qrencode >/dev/null 2>&1 || {
    echo "qrencode not installed; skip --qr" >&2; exit 0; }
  qr_out="${CLIENT}.sub.qr.png"
  echo "$url" | qrencode -t PNG -o "$qr_out"
  echo "QR rendered: $qr_out"
fi

# Audit-log the issuance without blocking token delivery if local logging is
# unavailable.
note="hash=${token_hash:0:16} expires=${EXPIRES:-none} qr=${EMIT_QR} refresh=${REFRESH_TOKEN:+yes}"
ENV="$ENV" PROVIDER="$PROVIDER" \
  "${REPO_ROOT}/scripts/audit-log.sh" append-best-effort \
    --action issue-sub-token \
    --client "$CLIENT" \
    --note "$note"
