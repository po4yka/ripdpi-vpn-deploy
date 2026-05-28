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
TF_DIR="${REPO_ROOT}/terraform/providers/${PROVIDER}"

ip="$(terraform -chdir="$TF_DIR" output -raw server_ipv4 2>/dev/null || true)"
admin="$(terraform -chdir="$TF_DIR" output -raw admin_user 2>/dev/null || echo admin)"
if ! [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "no IP available for ${PROVIDER}:${ENV}" >&2
  exit 2
fi

today="$(date -u +%Y-%m-%d)"
local_out="${REPO_ROOT}/reports/probing-${PROVIDER}-${ENV}-${today}.md"
mkdir -p "${REPO_ROOT}/reports"

ssh_opts=(-o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new)

# Pipe the aggregator script over stdin to avoid a world-readable /tmp drop
# (scp-to-/tmp + sudo python3 /tmp/script is a root TOCTOU). The script is
# executed entirely in memory; no file is written to the remote /tmp.
ssh "${ssh_opts[@]}" "${admin}@${ip}" \
  "sudo python3 - && sudo cat /var/log/vpn-probing-summary-${today}.md" \
  < "${REPO_ROOT}/scripts/probing-summary-remote.py" \
  > "$local_out"

echo "wrote $local_out"
echo
head -20 "$local_out"
