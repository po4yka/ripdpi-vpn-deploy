#!/usr/bin/env bash
# Summary table across every host/env pair in HOSTS. Useful when you have
# more than one VPS in the fleet (a second-region fallback, a staging
# node, a blue-green spare) and want a single screen showing version
# drift, last-deploy time, and reachability without ssh'ing into each.
#
# Usage:
#   HOSTS="upcloud:prod,hetzner:prod" scripts/fleet-status.sh
#   scripts/fleet-status.sh                  # equivalent to HOSTS=upcloud:prod
#
# Columns:
#   PROV  ENV  IP             ASN     xray_ver       last_deploy  watchdog  burn
#
# All ssh calls use the admin_user exported by each terraform root, and
# are bounded by a short ConnectTimeout so a single dead node doesn't
# block the whole run.
set -euo pipefail

# Portable bounded-run wrapper. macOS lacks `timeout` (coreutils ships it as
# `gtimeout`); use that, or run without a limit if neither is present. On Linux
# this resolves to `timeout`, so behaviour there is unchanged.
run_timeout() {
  local secs="$1"; shift
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
IFS=',' read -r -a host_pairs <<< "$HOSTS"

ssh_opts=(-o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new)

printf '%-9s %-7s %-15s %-9s %-14s %-20s %-9s %s\n' \
  PROV ENV IP ASN XRAY_VER LAST_DEPLOY WATCHDOG BURN
printf '%-9s %-7s %-15s %-9s %-14s %-20s %-9s %s\n' \
  ---- --- -- --- -------- ----------- -------- ----

for pair in "${host_pairs[@]}"; do
  prov="${pair%:*}"
  env="${pair#*:}"
  tf_dir="${REPO_ROOT}/terraform/providers/${prov}"

  ip=""; admin=""
  if [[ -d "$tf_dir" ]]; then
    ip="$(terraform -chdir="$tf_dir" output -raw server_ipv4 2>/dev/null || true)"
    admin="$(terraform -chdir="$tf_dir" output -raw admin_user 2>/dev/null || echo admin)"
  fi
  # Some terraform versions emit "Warning: No outputs found" on stdout even
  # when output -raw missed — only proceed if we got a real dotted-quad.
  if ! [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    printf '%-9s %-7s %-15s %-9s %-14s %-20s %-9s %s\n' \
      "$prov" "$env" "(no tfout)" "-" "-" "-" "-" "-"
    continue
  fi

  # ASN via Cymru (best effort; one shell-out)
  asn="-"
  asn_line="$("${REPO_ROOT}/scripts/probe-asn.sh" "$ip" 2>/dev/null || true)"
  if [[ -n "$asn_line" ]]; then
    asn="AS$(echo "$asn_line" | awk -F'\t' '{print $2}')"
  fi

  remote="$(ssh "${ssh_opts[@]}" "${admin}@${ip}" '
    set -e
    xv="$(/usr/local/bin/xray version 2>/dev/null | head -1 | awk "{print \$2}" || echo "?")"
    last="$(stat -c %y /etc/xray/config.json 2>/dev/null | cut -d. -f1 || echo "?")"
    if systemctl is-active --quiet vpn-watchdog.service 2>/dev/null; then
      wd=ok
    elif systemctl is-active --quiet vpn-watchdog.timer 2>/dev/null; then
      wd=ok
    else
      wd=fail
    fi
    echo "$xv|$last|$wd"
  ' 2>/dev/null || echo "?|?|?")"

  xv="$(echo "$remote" | awk -F'|' '{print $1}')"
  last="$(echo "$remote" | awk -F'|' '{print $2}')"
  wd="$(echo "$remote" | awk -F'|' '{print $3}')"

  burn="-"
  # Skip live burn-check (paid API surface): just show TCP-reachable
  # by trying a local short connect.
  if run_timeout 5 bash -c "</dev/tcp/${ip}/443" 2>/dev/null; then
    burn=reachable
  else
    burn=blocked
  fi

  printf '%-9s %-7s %-15s %-9s %-14s %-20s %-9s %s\n' \
    "$prov" "$env" "$ip" "$asn" "$xv" "$last" "$wd" "$burn"
done
