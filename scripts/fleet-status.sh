#!/usr/bin/env bash
# Read-only declared and observed status for every provider:environment pair.
#
# Usage:
#   HOSTS="upcloud:prod,hetzner:stage" scripts/fleet-status.sh [--json]
#   scripts/fleet-status.sh --help
set -euo pipefail

json_output=0
case "${1:-}" in
  "") ;;
  --json) json_output=1 ;;
  -h|--help)
    echo 'usage: HOSTS="provider:environment[,provider:environment]" scripts/fleet-status.sh [--json]'
    exit 0
    ;;
  *) echo "fleet-status: unknown argument: $1" >&2; exit 2 ;;
esac
[[ $# -le 1 ]] || { echo "fleet-status: only --json is supported" >&2; exit 2; }

run_timeout() {
  local secs="$1"
  shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "$secs" "$@"
  elif command -v gtimeout >/dev/null 2>&1; then
    gtimeout "$secs" "$@"
  else
    "$@"
  fi
}

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOSTS="${HOSTS:-${PROVIDER:-upcloud}:${ENV:-prod}}"
if [[ -z "$HOSTS" || "$HOSTS" == ,* || "$HOSTS" == *, || "$HOSTS" == *,,* ]]; then
  echo "fleet-status: HOSTS must be a nonempty comma-separated list" >&2
  exit 2
fi
IFS=',' read -r -a host_pairs <<< "$HOSTS"

# Validate the complete input before any Terraform, SSH, ASN, or TCP command.
for pair in "${host_pairs[@]}"; do
  if [[ "$pair" != *:* || "$pair" == *:*:* ]]; then
    echo "fleet-status: each HOSTS entry must contain exactly one colon" >&2
    exit 2
  fi
  prov="${pair%%:*}"
  env="${pair#*:}"
  case "$prov" in
    upcloud|hetzner|vultr) ;;
    *) echo "fleet-status: unsupported provider" >&2; exit 2 ;;
  esac
  if ! [[ "$env" =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ ]]; then
    echo "fleet-status: environment must be a technical slug" >&2
    exit 2
  fi
done

umask 077
records_file="$(mktemp -t fleet-status.XXXXXX)"
trap 'rm -f "$records_file"' EXIT
ssh_opts=(-o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new)

append_record() {
  local prov="$1" env="$2" address="$3" tf_status="$4" ssh_status="$5"
  local asn="$6" xray_version="$7" config_updated_at="$8" watchdog="$9"
  local tcp_443="${10}" manifest_available="${11}" manifest_base64="${12}"
  printf '%s' "$manifest_base64" | python3 "${REPO_ROOT}/scripts/fleet_status.py" record \
    --provider "$prov" \
    --environment "$env" \
    --address "$address" \
    --terraform-output "$tf_status" \
    --ssh "$ssh_status" \
    --asn "$asn" \
    --xray-version "$xray_version" \
    --config-updated-at "$config_updated_at" \
    --watchdog "$watchdog" \
    --tcp-443 "$tcp_443" \
    --manifest-available "$manifest_available" >> "$records_file"
}

for pair in "${host_pairs[@]}"; do
  prov="${pair%%:*}"
  env="${pair#*:}"
  ip="$(PROVIDER="$prov" ENV="$env" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw server_ipv4 2>/dev/null || true)"
  if ! [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    append_record "$prov" "$env" "" missing not_attempted "" "" "" unknown not_probed false ""
    continue
  fi

  admin="$(PROVIDER="$prov" ENV="$env" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw admin_user 2>/dev/null || true)"
  [[ -n "$admin" ]] || admin="admin"

  asn=""
  asn_line="$("${REPO_ROOT}/scripts/probe-asn.sh" "$ip" 2>/dev/null || true)"
  asn_number="$(printf '%s\n' "$asn_line" | awk -F'\t' 'NR==1 {print $2}')"
  if [[ "$asn_number" =~ ^[0-9]+$ ]]; then
    asn="AS${asn_number}"
  fi

  ssh_status=unreachable
  xray_version=""
  config_updated_at=""
  watchdog=unknown
  manifest_available=false
  manifest_base64=""
  if remote="$(ssh "${ssh_opts[@]}" "${admin}@${ip}" '
    xv="$(/usr/local/bin/xray version 2>/dev/null | head -1 | awk "{print \$2}" || true)"
    updated="$(stat -c %y /etc/xray/config.json 2>/dev/null | cut -d. -f1 || true)"
    if systemctl is-active --quiet vpn-watchdog.service 2>/dev/null || systemctl is-active --quiet vpn-watchdog.timer 2>/dev/null; then
      wd=ok
    elif command -v systemctl >/dev/null 2>&1; then
      wd=fail
    else
      wd=unknown
    fi
    manifest_path=/var/lib/ripdpi-vpn-deploy/manifest.json
    encoded=""
    if [ -f "$manifest_path" ]; then
      if base64 -w0 /dev/null >/dev/null 2>&1; then
        encoded="$(base64 -w0 "$manifest_path" 2>/dev/null || true)"
      else
        encoded="$(base64 "$manifest_path" 2>/dev/null | tr -d "\n" || true)"
      fi
    fi
    printf "%s|%s|%s|%s\n" "$xv" "$updated" "$wd" "$encoded"
  ' 2>/dev/null)"; then
    ssh_status=ok
    manifest_available=true
    IFS='|' read -r xray_version config_updated_at watchdog manifest_base64 <<< "$remote"
  fi

  tcp_443=blocked
  if run_timeout 5 bash -c "</dev/tcp/${ip}/443" 2>/dev/null; then
    tcp_443=reachable
  fi

  append_record "$prov" "$env" "$ip" ok "$ssh_status" "$asn" \
    "$xray_version" "$config_updated_at" "$watchdog" "$tcp_443" \
    "$manifest_available" "$manifest_base64"
done

render_args=(render)
[[ "$json_output" -eq 0 ]] || render_args+=(--json)
python3 "${REPO_ROOT}/scripts/fleet_status.py" "${render_args[@]}" < "$records_file"
