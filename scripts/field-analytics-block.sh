#!/usr/bin/env bash
# Block or unblock one protocol port on a staging node for the field-analytics
# acceptance run (docs/how-to/field-analytics-acceptance.md).
#
#   ENV=staging PROVIDER=upcloud L4=tcp PORT=443 MODE=drop scripts/field-analytics-block.sh plan
#   ... APPLY=1 scripts/field-analytics-block.sh block
#   ENV=staging PROVIDER=upcloud APPLY=1 scripts/field-analytics-block.sh unblock
#   ENV=staging PROVIDER=upcloud scripts/field-analytics-block.sh show
#
# The block lives in its own nftables table, inet ripdpi_acceptance, whose
# input hook runs before the firewall role's table. unblock deletes that whole
# table, so it never edits the managed ruleset. MODE=drop silently drops the
# packets; MODE=rst answers TCP with a reset (TCP only). SOURCE limits the
# block to one client address or prefix, so other clients keep the path.
# Without APPLY=1, block and unblock print what they would send and contact
# nothing. A production environment is refused.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROVIDER="${PROVIDER:-upcloud}"
ENV="${ENV:-}"
APPLY="${APPLY:-0}"
TABLE="ripdpi_acceptance"
verb="${1:-}"

die() { echo "field-analytics-block: $*" >&2; exit 2; }

[[ "$verb" =~ ^(plan|block|unblock|show)$ ]] || die "usage: $0 plan|block|unblock|show"
[[ "$ENV" =~ ^[a-z][a-z0-9-]{0,31}$ ]] || die "ENV must name a staging environment"
[[ "$ENV" != prod && "$ENV" != production ]] || die "refusing a production environment"
[[ "$APPLY" == 0 || "$APPLY" == 1 ]] || die "APPLY must be 0 or 1"

ruleset() {
  local l4="${L4:-}" port="${PORT:-}" mode="${MODE:-}" source="${SOURCE:-}" match verdict
  [[ "$l4" == tcp || "$l4" == udp ]] || die "L4 must be tcp or udp"
  [[ "$port" =~ ^[1-9][0-9]{0,4}$ ]] && (( port <= 65535 )) || die "PORT must be 1-65535"
  [[ "$port" != 22 ]] || die "refusing to block the SSH port"
  case "$mode" in
    drop) verdict="drop" ;;
    rst) [[ "$l4" == tcp ]] || die "MODE=rst needs L4=tcp"; verdict="reject with tcp reset" ;;
    *) die "MODE must be drop or rst" ;;
  esac
  match="$l4 dport $port"
  if [[ -n "$source" ]]; then
    python3 -c 'import ipaddress, sys; ipaddress.ip_network(sys.argv[1], strict=False)' "$source" 2>/dev/null \
      || die "SOURCE must be an IP address or prefix"
    if [[ "$source" == *:* ]]; then match="ip6 saddr $source $match"; else match="ip saddr $source $match"; fi
  fi
  # Delete-then-add keeps a second block run idempotent: the table holds exactly one rule.
  printf 'table inet %s\ndelete table inet %s\n' "$TABLE" "$TABLE"
  printf 'table inet %s {\n  chain input {\n    type filter hook input priority -10; policy accept;\n    %s counter %s\n  }\n}\n' \
    "$TABLE" "$match" "$verdict"
}

case "$verb" in
  plan) ruleset; exit 0 ;;
  block) payload="$(ruleset)"; remote="sudo nft -f -" ;;
  unblock) payload=""; remote="sudo nft delete table inet $TABLE 2>/dev/null || true; ! sudo nft list table inet $TABLE >/dev/null 2>&1" ;;
  show) payload=""; remote="sudo nft list table inet $TABLE 2>/dev/null || echo 'no acceptance block'" ;;
esac

if [[ "$verb" != show && "$APPLY" != 1 ]]; then
  echo "plan only (set APPLY=1 to send): ${verb} on ${PROVIDER}:${ENV}"
  [[ -z "$payload" ]] || printf '%s\n' "$payload"
  exit 0
fi

ip="$(PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw server_ipv4 2>/dev/null || true)"
admin="$(PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw admin_user 2>/dev/null || echo admin)"
[[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "no IP available for ${PROVIDER}:${ENV}" >&2; exit 2; }
[[ "$admin" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || { echo "unsafe admin user for ${PROVIDER}:${ENV}" >&2; exit 2; }

ssh_opts=(-o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new)
printf '%s' "$payload" | ssh "${ssh_opts[@]}" "${admin}@${ip}" "$remote"
echo "${verb}: done on ${PROVIDER}:${ENV} at $(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [[ "$verb" != show ]]; then
  ENV="$ENV" PROVIDER="$PROVIDER" \
    "${REPO_ROOT}/scripts/audit-log.sh" append-best-effort \
      --action "field-analytics-${verb}" \
      --note "table=${TABLE}"
fi
