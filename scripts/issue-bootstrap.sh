#!/usr/bin/env bash
# Issue a one-time bootstrap token for a single client. Emits the
# sing-box JSON over authenticated TLS, stores it under the token hash,
# drops the payload at the bootstrap host
# through SSH, and prints the URL the client should fetch.
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

# QR payloads contain credentials; create them owner-only.
umask 077

CLIENT="${1:-}"
[[ "$CLIENT" =~ ^[A-Za-z0-9_-]{1,64}$ ]] || { echo "client name must contain only letters, digits, underscores, or dashes" >&2; exit 1; }
[[ -n "$CLIENT" && "$CLIENT" != "-h" && "$CLIENT" != "--help" ]] || {
  sed -n '2,/^set -euo/p' "$0" | sed '$d' >&2
  exit 1
}
shift

EXPIRES=""
EMIT_QR=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --expires) [[ $# -ge 2 ]] || { echo "--expires requires YYYY-MM-DD" >&2; exit 2; }; EXPIRES="$2"; shift 2 ;;
    --qr)      EMIT_QR=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROVIDER="${PROVIDER:-upcloud}"
ENV="${ENV:-prod}"
SUBSCRIPTION_DIR="${SUBSCRIPTION_DIR:-/var/lib/vpn-subscription}"
# This path is interpolated into remote root commands; reject shell syntax.
if [[ ! "$SUBSCRIPTION_DIR" =~ ^/[A-Za-z0-9_][A-Za-z0-9_./-]*$ ]] || [[ "$SUBSCRIPTION_DIR" == *..* ]]; then
  echo "SUBSCRIPTION_DIR must be an absolute path using only [A-Za-z0-9_./-], with no '..'" >&2
  exit 2
fi

if [[ -n "$EXPIRES" ]]; then
  python3 - "$EXPIRES" <<'PY'
import datetime, sys
try:
    value = datetime.date.fromisoformat(sys.argv[1])
    assert value.isoformat() == sys.argv[1]
except (ValueError, AssertionError):
    raise SystemExit("expiry must be YYYY-MM-DD")
PY
fi

server_ip="$(PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw server_ipv4)"
admin_user="$(PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw admin_user 2>/dev/null || echo admin)"
server_hostname="$(PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw server_hostname 2>/dev/null || echo "$server_ip")"

payload="$("${REPO_ROOT}/scripts/emit-singbox.sh" "$CLIENT")"
[[ -n "$payload" ]] || { echo "empty payload from emit-singbox.sh" >&2; exit 1; }

# Server stores under sha256(token) so the plaintext token never touches
# disk. The hash is computed identically by the Python service on every
# inbound request — see ansible/roles/subscription-host/templates/
# vpn-bootstrap.py.j2.
# Resolve the effective role policy and optional encrypted override in memory.
sops_file="${SOPS_FILE:-${HOME}/.config/vpn-provision/${ENV}.secrets.sops.yaml}"
subscription_config="$(sops --decrypt --output-type json "$sops_file" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); s=d.get('subscription') or {}; print(json.dumps({'_replace_policy':'subscription' in d, 'server_name':s.get('server_name') or (d.get('nginx_xhttp') or {}).get('server_name') or '', **({'bootstrap_max_lifetime_seconds':s['bootstrap_max_lifetime_seconds']} if 'bootstrap_max_lifetime_seconds' in s else {})}))")"
sub_host="$(printf '%s' "$subscription_config" | python3 -c 'import sys,json; print(json.load(sys.stdin)["server_name"])')"
[[ -n "$sub_host" ]] || sub_host="$server_hostname"
sub_port="$(python3 "${REPO_ROOT}/scripts/resolve-subscription-port.py" --host "$server_hostname")"
grant="$(printf '%s' "$subscription_config" | python3 "${REPO_ROOT}/scripts/resolve-subscription-port.py" --host "$server_hostname" --bootstrap-grant --expires "$EXPIRES")"
token="$(printf '%s' "$grant" | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')"
expiry_epoch="$(printf '%s' "$grant" | python3 -c 'import sys,json; print(json.load(sys.stdin)["expires"])')"
token_hash="$(printf '%s' "$token" | shasum -a 256 2>/dev/null | awk '{print $1}')"
if [[ -z "$token_hash" ]]; then
  token_hash="$(printf '%s' "$token" | sha256sum | awk '{print $1}')"
fi
remote_path="${SUBSCRIPTION_DIR}/bootstrap/${token_hash}"

# See issue-sub-token.sh: mirrored generations do not consume legacy direct
# writes, so fail closed before installing a bearer payload.
if ! ssh "${admin_user}@${server_ip}" \
  "sudo test ! -e '${SUBSCRIPTION_DIR}/.vpn-sub-mirror-generations' -a ! -L '${SUBSCRIPTION_DIR}/.vpn-sub-mirror-current'"; then
  echo "error: subscription mirror mode is active; direct token issuance is unavailable" >&2
  exit 1
fi

# Publish the bounded deadline first; interrupted issuance cannot create an
# unbounded grant. The token timestamp remains authoritative if metadata is lost.
meta="{\"expires\":${expiry_epoch}}"
printf '%s' "$meta" | ssh "${admin_user}@${server_ip}" \
  "sudo install -o vpn-bootstrap -g vpn-bootstrap -m 0600 /dev/stdin '${remote_path}.meta'"
printf '%s' "$payload" | ssh "${admin_user}@${server_ip}" \
  "sudo install -o vpn-bootstrap -g vpn-bootstrap -m 0600 /dev/stdin '${remote_path}'"

echo "stored hash: ${token_hash:0:8}…  path: ${remote_path}"

url="https://${sub_host}:${sub_port}/bootstrap/${token}"

echo
echo "Bootstrap URL (one-time, copy to client now):"
echo "  $url"
echo
echo "Properties:"
echo "  * consumed on first successful GET (second fetch → 410)"
echo "  * intrinsic expiry epoch: ${expiry_epoch} (metadata cannot extend it)"
if [[ -n "$EXPIRES" ]]; then
  echo "  * server-side expiry: ${EXPIRES} (410 after that date)"
fi

if (( EMIT_QR )); then
  command -v qrencode >/dev/null 2>&1 || {
    echo "qrencode not installed; skip --qr" >&2; exit 0; }
  qr_out="${CLIENT}.bootstrap.qr.png"
  # Replace atomically so legacy 0644 files never expose the new payload.
  (
    qr_tmp="$(mktemp "${qr_out}.XXXXXX")"
    trap 'rm -f "$qr_tmp"' EXIT
    echo "$url" | qrencode -t PNG -o "$qr_tmp"
    chmod 0600 "$qr_tmp"
    python3 -c 'import os, sys; os.replace(sys.argv[1], sys.argv[2])' "$qr_tmp" "$qr_out"
  )
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
