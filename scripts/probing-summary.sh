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
#   reports/probing-<host>-YYYY-MM-DD.md is on the workstation
#   the Prometheus textfile is updated on the VPS
set -euo pipefail

PROVIDER="${PROVIDER:-upcloud}"
ENV="${ENV:-prod}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

ip="$(PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw server_ipv4 2>/dev/null || true)"
admin="$(PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw admin_user 2>/dev/null || echo admin)"
if ! [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "no IP available for ${PROVIDER}:${ENV}" >&2
  exit 2
fi

today="$(date -u +%Y-%m-%d)"
local_out="${REPO_ROOT}/reports/probing-${PROVIDER}-${ENV}-${today}.md"
mkdir -p "${REPO_ROOT}/reports"

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
