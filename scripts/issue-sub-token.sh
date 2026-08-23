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
#   scripts/issue-sub-token.sh phone --format ripdpi --expires 2026-12-31 --qr
#   scripts/issue-sub-token.sh phone --refresh-token <existing-token>
#     (refresh reuses the original format/hosts/cohorts recorded in the
#      encrypted client_registry; explicit flags override and are logged)
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
FORMAT="singbox"
FORMAT_SET=0
EXPIRES_SET=0
EMIT_QR=0
REFRESH_TOKEN=""
PRINT_TOKEN_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --expires)          EXPIRES="$2"; EXPIRES_SET=1; shift 2 ;;
    --format)           FORMAT="$2"; FORMAT_SET=1; shift 2 ;;
    --qr)               EMIT_QR=1; shift ;;
    --refresh-token)    REFRESH_TOKEN="$2"; shift 2 ;;
    --print-token-only) PRINT_TOKEN_ONLY=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
case "$FORMAT" in
  singbox|ripdpi) ;;
  *) echo "format must be singbox or ripdpi" >&2; exit 1 ;;
esac
if [[ -n "$EXPIRES" ]]; then
  EXPIRES="$(python3 "${REPO_ROOT}/scripts/normalize-subscription-expiry.py" "$EXPIRES")"
fi
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
hash_prefix="${token_hash:0:8}"

sops_file="${SOPS_FILE:-${HOME}/.config/vpn-provision/${ENV}.secrets.sops.yaml}"
sops_file="$(SOPS_FILE="$sops_file" python3 -c 'import os; print(os.path.realpath(os.environ["SOPS_FILE"]))')"
if [[ ! -f "$sops_file" ]]; then
  echo "missing $sops_file" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Registry resolution — refreshes MUST reuse the original issuance options.
# A bare --refresh-token reuses only the bearer token; format, hosts, and
# cohorts would otherwise reset to defaults and overwrite a multi-host or
# ripdpi subscription with a wrong single-host sing-box payload.
# ---------------------------------------------------------------------------
REGISTRY_HOSTS=""
REGISTRY_COHORTS=""
OVERRIDDEN=""
REUSED=""
if [[ -n "$REFRESH_TOKEN" ]]; then
  registry_state="$(sops --decrypt --extract '["client_registry"]' --output-type json "$sops_file" 2>/dev/null || echo '{}')"

  resolved="$(TOKEN_PREFIX="$hash_prefix" CLIENT_NAME="$CLIENT" python3 -c '
import json, os, sys

registry = json.loads(sys.stdin.read() or "{}")
# sops --extract normally returns the subtree itself; tolerate a full
# document too (older sops builds and the test stub behave this way).
if "client_registry" in registry and isinstance(registry["client_registry"], dict):
    registry = registry["client_registry"]
matches = [
    entry for name, entry in registry.items()
    if isinstance(entry, dict)
    and (entry.get("token_hash_prefix") or "") == os.environ["TOKEN_PREFIX"]
]
if not matches:
    client = os.environ["CLIENT_NAME"]
    prefix = os.environ["TOKEN_PREFIX"]
    raise SystemExit(
        "error: no client_registry entry for client %r with token hash "
        "prefix %r; refresh refused — re-issue the token instead"
        % (client, prefix)
    )
if len(matches) > 1:
    raise SystemExit("error: ambiguous client_registry entries for this token prefix; re-issue")
entry = matches[0]
formats = entry.get("formats") or []
hosts = entry.get("hosts") or []
cohorts = entry.get("cohorts") or []
if not formats or not hosts:
    raise SystemExit("error: registry entry lacks formats or hosts; re-issue the token")
print(formats[-1])
print(",".join(hosts))
print(",".join(cohorts))
' 2>&1 <<<"$registry_state")" || {
    echo "$resolved" >&2
    exit 1
  }
  {
    IFS= read -r registry_format || true
    IFS= read -r registry_hosts || true
    IFS= read -r registry_cohorts || true
  } <<<"$resolved"

  if (( FORMAT_SET )); then
    OVERRIDDEN="format"
  else
    FORMAT="$registry_format"
    REUSED="format"
  fi
  if (( EXPIRES_SET )); then
    OVERRIDDEN="${OVERRIDDEN:+$OVERRIDDEN,}expires"
  else
    REUSED="${REUSED:+$REUSED,}expires"
  fi
  REGISTRY_HOSTS="$registry_hosts"
  REGISTRY_COHORTS="$registry_cohorts"
  echo "refresh options — reused: ${REUSED:-none}; overridden: ${OVERRIDDEN:-none}"
  echo "refresh payload format: ${FORMAT}; hosts: ${REGISTRY_HOSTS}${REGISTRY_COHORTS:+; cohorts: ${REGISTRY_COHORTS}}"
fi

EMITTER_ENV=()
if [[ -n "$REGISTRY_HOSTS" ]]; then
  EMITTER_ENV+=(HOSTS="$REGISTRY_HOSTS")
fi
if [[ -n "$REGISTRY_COHORTS" ]]; then
  EMITTER_ENV+=(COHORTS="$REGISTRY_COHORTS")
fi

if [[ "$FORMAT" == "ripdpi" ]]; then
  payload="$(env "${EMITTER_ENV[@]}" BUNDLE_EXPIRES="$EXPIRES" \
    "${REPO_ROOT}/scripts/emit-bundle.sh" "$CLIENT")"
  emitter="emit-bundle.sh"
else
  payload="$(env "${EMITTER_ENV[@]}" \
    "${REPO_ROOT}/scripts/emit-singbox.sh" "$CLIENT")"
  emitter="emit-singbox.sh"
fi
[[ -n "$payload" ]] || { echo "empty payload from ${emitter}" >&2; exit 1; }

remote_path="${SUBSCRIPTION_DIR}/sub/${token_hash}"

printf '%s' "$payload" | ssh "${admin_user}@${server_ip}" \
  "sudo install -o vpn-bootstrap -g vpn-bootstrap -m 0600 /dev/stdin '${remote_path}'"

if [[ -n "$EXPIRES" ]]; then
  meta="$(jq -nc --arg expires "$EXPIRES" --arg client "$CLIENT" '{expires: $expires, client: $client}')"
  printf '%s' "$meta" | ssh "${admin_user}@${server_ip}" \
    "sudo install -o vpn-bootstrap -g vpn-bootstrap -m 0600 /dev/stdin '${remote_path}.meta'"
fi

# ---------------------------------------------------------------------------
# Record the issuance in the encrypted client_registry. Uses the same
# transaction lock as new-client.sh so concurrent SOPS edits serialize.
# ---------------------------------------------------------------------------
REGISTRY_LOCK="${sops_file}.new-client.lock"
REGISTRY_TEMP=""
cleanup_registry() {
  if [[ -n "$REGISTRY_TEMP" ]]; then
    rm -f -- "$REGISTRY_TEMP"
  fi
}
trap cleanup_registry EXIT
exec 8> "$REGISTRY_LOCK"
if command -v flock >/dev/null 2>&1; then
  registry_lock_command=(flock -n 8)
elif command -v lockf >/dev/null 2>&1; then
  registry_lock_command=(lockf -s -t 0 8)
else
  echo "error: issue-sub-token requires flock (Linux) or lockf (macOS)" >&2
  exit 1
fi
if ! "${registry_lock_command[@]}"; then
  echo "error: another secrets transaction is active for $sops_file" >&2
  exit 1
fi

registry_temp="$(SOPS_FILE="$sops_file" python3 -c '
import os, pathlib, tempfile

path = os.path.abspath(os.environ["SOPS_FILE"])
suffix = pathlib.Path(path).suffix or ".yaml"
fd, temporary = tempfile.mkstemp(prefix=f".{os.path.basename(path)}.issue-sub.", suffix=suffix, dir=os.path.dirname(path))
os.close(fd)
print(temporary)
')"
REGISTRY_TEMP="$registry_temp"
cp "$sops_file" "$registry_temp"
chmod 0600 "$registry_temp"

entry_json="$(FORMAT="$FORMAT" HOSTS="${REGISTRY_HOSTS:-${PROVIDER}:${ENV}}" \
  COHORTS="$REGISTRY_COHORTS" HASH_PREFIX="$hash_prefix" EXPIRY="$EXPIRES" \
  python3 <<PYEOF
import json, os
from datetime import datetime, timezone
import subprocess

entry = {
    "status": "delivered",
    "issued_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "formats": [os.environ["FORMAT"]],
    "hosts": [h for h in os.environ["HOSTS"].split(",") if h],
    "cohorts": [c for c in os.environ["COHORTS"].split(",") if c],
    "token_hash_prefix": os.environ["HASH_PREFIX"],
    "token_expires": os.environ["EXPIRY"],
}
existing = json.loads(subprocess.run(
    ["sops", "--decrypt", "--extract", '["client_registry"]', "--output-type", "json", "$sops_file"],
    capture_output=True, text=True,
).stdout or "{}").get("$CLIENT") or {}
merged = {**existing, **{k: v for k, v in entry.items()}}
# Preserve prior formats when refreshing with a reused format.
if existing.get("formats") and os.environ["FORMAT"] in existing["formats"]:
    merged["formats"] = existing["formats"]
elif existing.get("formats"):
    merged["formats"] = sorted(set(existing["formats"]) | set(entry["formats"]))
print(json.dumps(merged))
PYEOF
)"

printf '%s' "$entry_json" | sops set --value-stdin "$registry_temp" "[\"client_registry\"][\"$CLIENT\"]"

mv -f -- "$registry_temp" "$sops_file"
REGISTRY_TEMP=""

# Pull subscription host name + port from secrets so the URL goes to
# the subscription endpoint, not the transport one.
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
echo "  * payload format: ${FORMAT}"
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
if [[ -n "$REFRESH_TOKEN" ]]; then
  options_note="options=reused:${REUSED:-none};overridden:${OVERRIDDEN:-none}"
else
  options_note="options=issued:format=${FORMAT},hosts=${REGISTRY_HOSTS:-${PROVIDER}:${ENV}}"
fi
note="hash=${token_hash:0:16} expires=${EXPIRES:-none} format=${FORMAT} qr=${EMIT_QR} refresh=${REFRESH_TOKEN:+yes} ${options_note}"
ENV="$ENV" PROVIDER="$PROVIDER" \
  "${REPO_ROOT}/scripts/audit-log.sh" append-best-effort \
    --action issue-sub-token \
    --client "$CLIENT" \
    --note "$note"
