#!/usr/bin/env bash
# Pull a 7-day probing summary from the deployed VPS. Pushes the
# probing-summary-remote.py aggregator over ssh, runs it server-side
# (where the logs live), and copies the rendered markdown back to the
# operator workstation.
#
# Usage:
#   PROVIDER=upcloud ENV=prod scripts/probing-summary.sh
#
# After run:
#   ${XDG_STATE_HOME:-~/.local/state}/vpn-provision/reports/probing-<provider>-<env>-YYYY-MM-DD.md
#   is on the workstation, mode 0600. It is outside the repository and its
#   name has no address, so a node address cannot reach a commit this way.
#   the Prometheus textfile is updated on the VPS
# IP optionally selects an explicit public IPv4 address instead of the primary node.
set -euo pipefail

PROVIDER="${PROVIDER:-upcloud}"
ENV="${ENV:-prod}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

ip="${IP:-}"
if [[ -z "$ip" ]]; then
  ip="$(PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw server_ipv4 2>/dev/null || true)"
fi
admin="$(PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw admin_user 2>/dev/null || echo admin)"
if ! [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "no IP available for ${PROVIDER}:${ENV}" >&2
  exit 2
fi

today="$(date -u +%Y-%m-%d)"
host_suffix=""
# An explicit host gets its own report. Its name carries nothing derived from the address.
[[ -z "${IP:-}" ]] || host_suffix="-explicit-host"
umask 077
report_dir="${XDG_STATE_HOME:-${HOME}/.local/state}/vpn-provision/reports"
mkdir -p "$report_dir"
local_out="${report_dir}/probing-${PROVIDER}-${ENV}${host_suffix}-${today}.md"
: > "$local_out"
chmod 0600 "$local_out"   # a report from an earlier version can have a wider mode

# StrictHostKeyChecking=accept-new: trusts the host key on first connect and
# rejects changed keys thereafter. This lowers friction on reprovisioned nodes
# (new VPS, same IP, rotated host key) because the operator must manually
# clear the known_hosts entry rather than the script silently accepting a
# potentially MITMed key. Use StrictHostKeyChecking=yes with a pre-seeded
# known_hosts entry if you need stronger TOFU enforcement.
ssh_opts=(-o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new)

# Pipe the aggregator script over stdin to avoid a world-readable /tmp drop
# (scp-to-/tmp + sudo python3 /tmp/script is a root TOCTOU). The script is
# executed entirely in memory; no file is written to the remote /tmp.
# Run the aggregator first, discarding its status stdout, then fetch the report
# in a SEPARATE call. Merging both into one stdout (as `python3 - && cat`) would
# prepend the aggregator's "wrote ..." status lines to the markdown report.
ssh "${ssh_opts[@]}" "${admin}@${ip}" "sudo python3 - >/dev/null" \
  < "${REPO_ROOT}/scripts/probing-summary-remote.py"
ssh "${ssh_opts[@]}" "${admin}@${ip}" \
  "sudo cat /var/log/vpn-probing-summary-${today}.md" \
  > "$local_out"

echo "wrote $local_out"
echo
head -20 "$local_out"
