#!/usr/bin/env bash
# Pull the server-side subscription read-audit log from the VPS and
# print it as JSONL. Per-record fields:
#   ts          unix epoch
#   iso         RFC-3339 timestamp
#   route       sub | bootstrap
#   token_prefix  first 8 chars of the sha256 hash (correlation key)
#   outcome     consumed | unknown | revoked | expired
#   src_ip      visitor IP (X-Real-IP if nginx forwarded it)
#   bytes       payload size served (0 on rejection)
#
# Operator workflow:
#   make sub-reads                # last 24h
#   make sub-reads SINCE="2026-05-01"
#   scripts/sub-reads.sh --since "2026-05-01" --route sub
#
# The log is owned by vpn-bootstrap on the VPS; the script sudo-tails
# it. Records are never decrypted to disk — they're streamed through
# ssh straight to stdout.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROVIDER="${PROVIDER:-upcloud}"
ENV="${ENV:-prod}"

SINCE=""
ROUTE=""
LIMIT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --since) SINCE="$2"; shift 2 ;;
    --route) ROUTE="$2"; shift 2 ;;
    --limit) LIMIT="$2"; shift 2 ;;
    -h|--help) sed -n '2,/^set -euo/p' "$0" | sed '$d' >&2; exit 1 ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

ip="$(PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw server_ipv4 2>/dev/null || true)"
admin="$(PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw admin_user 2>/dev/null || echo admin)"
if ! [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "no IP available for ${PROVIDER}:${ENV}" >&2
  exit 2
fi

filter_args=()
[[ -n "$SINCE" ]] && filter_args+=(--since "$SINCE")
[[ -n "$ROUTE" ]] && filter_args+=(--route "$ROUTE")
[[ -n "$LIMIT" ]] && filter_args+=(--limit "$LIMIT")

ssh_opts=(-o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new)
ssh "${ssh_opts[@]}" "${admin}@${ip}" \
  "sudo cat /var/log/vpn-subscription/reads.log" \
  | python3 "${REPO_ROOT}/scripts/sub-reads-filter.py" "${filter_args[@]}"
