#!/usr/bin/env bash
# Coordinated fleet rotation. Drives scripts/blue-green.sh sequentially
# across every host in a fleet plan, while preserving a minimum number
# of healthy hosts at all times. Resumable: keeps state under
# .omc/state/fleet-rotate-<id>.json so a crash mid-rotation can pick up
# where it left off.
#
# Fleet plan format (YAML):
#
#   id: 2026-05-rotation
#   min_active: 1
#   rotations:
#     - current: upcloud:prod
#       new_env:  prod-2026-05
#       new_zone: nl-ams1
#     - current: hetzner:prod
#       new_env:  prod-2026-05
#       new_zone: hel1
#
# Usage:
#   scripts/fleet-rotate.sh --plan ~/.config/vpn-provision/fleet-rotate.yaml
#   scripts/fleet-rotate.sh --plan plan.yaml --resume   # pick up from state
#   scripts/fleet-rotate.sh --plan plan.yaml --dry-run  # validate plan only
#
# Approval gate fires between each rotation entry — the script will not
# proceed to host N+1 until the operator confirms host N completed.
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
STATE_DIR="${REPO_ROOT}/.omc/state"
mkdir -p "$STATE_DIR"

PLAN=""
RESUME=0
DRY_RUN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --plan)    PLAN="$2"; shift 2 ;;
    --resume)  RESUME=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help)
      sed -n '2,/^set -euo/p' "$0" | sed '$d' >&2
      exit 1 ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done
[[ -n "$PLAN" && -f "$PLAN" ]] || { echo "--plan FILE required" >&2; exit 1; }

for tool in python3 jq make; do
  command -v "$tool" >/dev/null 2>&1 || { echo "missing tool: $tool" >&2; exit 1; }
done

# ---------------------------------------------------------------------------
# Parse the plan (YAML → JSON) and derive a state-file path.
# ---------------------------------------------------------------------------
plan_json="$(python3 -c "
import json, yaml, sys
print(json.dumps(yaml.safe_load(open('$PLAN').read())))
")"
plan_id="$(jq -r '.id // "unnamed"' <<< "$plan_json")"
min_active="$(jq -r '.min_active // 1' <<< "$plan_json")"
total="$(jq -r '.rotations | length' <<< "$plan_json")"
STATE="${STATE_DIR}/fleet-rotate-${plan_id}.json"

if (( DRY_RUN )); then
  echo "plan id=${plan_id}  rotations=${total}  min_active=${min_active}"
  jq -r '.rotations | to_entries[] | "  \(.key+1)/'"$total"' \(.value.current) → ENV=\(.value.new_env) zone=\(.value.new_zone // "(same)")"' \
    <<< "$plan_json"
  exit 0
fi

if (( RESUME )) && [[ -f "$STATE" ]]; then
  start_idx="$(jq -r '.next_idx // 0' "$STATE")"
  echo "resuming at index ${start_idx} (state: $STATE)"
else
  start_idx=0
  jq -n --arg id "$plan_id" --argjson total "$total" --argjson min "$min_active" \
    '{id: $id, total: $total, min_active: $min, next_idx: 0, completed: []}' \
    > "$STATE"
fi

# ---------------------------------------------------------------------------
# Reachability census — used to enforce min_active.
# ---------------------------------------------------------------------------
count_reachable() {
  local ok=0
  local pairs
  pairs="$(jq -r '.rotations[] | .current' <<< "$plan_json")"
  while IFS= read -r pair; do
    [[ -z "$pair" ]] && continue
    local prov="${pair%:*}"
    local tf="${REPO_ROOT}/terraform/providers/${prov}"
    local ip
    ip="$(terraform -chdir="$tf" output -raw server_ipv4 2>/dev/null || true)"
    if [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] \
       && run_timeout 5 bash -c "</dev/tcp/$ip/443" 2>/dev/null; then
      ok=$((ok+1))
    fi
  done <<< "$pairs"
  echo "$ok"
}

confirm() {
  local prompt="$1"
  read -r -p "$prompt [yes/NO]: " ans
  [[ "$ans" == "yes" ]]
}

# ---------------------------------------------------------------------------
# Per-host rotation loop.
# ---------------------------------------------------------------------------
for idx in $(seq "$start_idx" $((total - 1))); do
  entry="$(jq -c ".rotations[$idx]" <<< "$plan_json")"
  current="$(jq -r '.current' <<< "$entry")"
  prov="${current%:*}"
  blue_env="${current#*:}"
  green_env="$(jq -r '.new_env' <<< "$entry")"
  green_zone="$(jq -r '.new_zone // ""' <<< "$entry")"

  echo
  echo "============================================================"
  echo "[$((idx+1))/$total]  ${prov}:${blue_env} → ENV=${green_env}  zone=${green_zone:-(same)}"
  echo "============================================================"

  reach_before="$(count_reachable)"
  echo "reachable hosts before this step: ${reach_before}"
  if (( reach_before < min_active )); then
    echo "FAIL: fleet already below min_active=${min_active}; refuse to rotate further" >&2
    exit 1
  fi

  if ! confirm "Proceed with rotating ${prov}:${blue_env}?"; then
    echo "stopped at index ${idx}; resume with --resume"
    exit 1
  fi

  PROVIDER="$prov" BLUE_ENV="$blue_env" GREEN_ENV="$green_env" \
    ${green_zone:+GREEN_ZONE="$green_zone"} \
    "${REPO_ROOT}/scripts/blue-green.sh"

  ENV="$blue_env" PROVIDER="$prov" \
    "${REPO_ROOT}/scripts/audit-log.sh" append-best-effort \
      --action fleet-rotate-step \
      --note "plan=${plan_id} index=$((idx+1))/${total} green_env=${green_env} green_zone=${green_zone:-same}"

  jq --argjson idx "$((idx+1))" --arg completed_entry "${prov}:${blue_env}→${green_env}" \
    '.next_idx = $idx | .completed += [$completed_entry]' \
    "$STATE" > "${STATE}.tmp" && mv "${STATE}.tmp" "$STATE"
done

echo
echo "fleet rotation complete (plan=${plan_id}, ${total} entries)"
echo "state file: $STATE"

"${REPO_ROOT}/scripts/audit-log.sh" append-best-effort \
  --action fleet-rotate-complete \
  --provider fleet \
  --note "plan=${plan_id} rotations=${total}"
