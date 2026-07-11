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
# Parse and validate the complete plan (YAML → normalized JSON) before any
# state or provider side effects.
# ---------------------------------------------------------------------------
plan_json="$(python3 - "$PLAN" <<'PY'
import json
import re
import sys
import yaml

SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,63}")
PROVIDERS = {"upcloud", "hetzner", "vultr"}


def fail(message):
    raise SystemExit(f"invalid fleet plan: {message}")


try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        plan = yaml.safe_load(handle)
except Exception as error:
    fail(f"could not parse YAML: {error}")

if not isinstance(plan, dict):
    fail("top level must be a mapping")
required = {"id", "min_active", "rotations"}
missing = required - plan.keys()
unknown = plan.keys() - required
if missing:
    fail(f"missing key: {sorted(missing)[0]}")
if unknown:
    fail(f"unknown key: {next(iter(unknown))!r}")

plan_id = plan["id"]
if not isinstance(plan_id, str) or not SLUG.fullmatch(plan_id):
    fail("id must be 1-64 letters, digits, or dashes and start with a letter or digit")

rotations = plan["rotations"]
if not isinstance(rotations, list) or not rotations:
    fail("rotations must be a non-empty list")

min_active = plan["min_active"]
if isinstance(min_active, bool) or not isinstance(min_active, int):
    fail("min_active must be an integer")
if not 1 <= min_active <= len(rotations):
    fail("min_active must be between 1 and the number of rotations")

seen_current = set()
for index, rotation in enumerate(rotations, start=1):
    label = f"rotation {index}"
    if not isinstance(rotation, dict):
        fail(f"{label} must be a mapping")
    allowed = {"current", "new_env", "new_zone"}
    required_rotation = {"current", "new_env"}
    missing = required_rotation - rotation.keys()
    unknown = rotation.keys() - allowed
    if missing:
        fail(f"{label} missing key: {sorted(missing)[0]}")
    if unknown:
        fail(f"{label} unknown key: {next(iter(unknown))!r}")

    current = rotation["current"]
    if not isinstance(current, str) or current.count(":") != 1:
        fail(f"{label} current must be PROVIDER:ENV")
    provider, current_env = current.split(":")
    if provider not in PROVIDERS:
        fail(f"{label} uses unsupported provider")
    if not SLUG.fullmatch(current_env):
        fail(f"{label} current environment is invalid")
    if current in seen_current:
        fail(f"duplicate current: {current}")
    seen_current.add(current)

    new_env = rotation["new_env"]
    if not isinstance(new_env, str) or not SLUG.fullmatch(new_env):
        fail(f"{label} new_env is invalid")
    if new_env == current_env:
        fail(f"{label} new_env must differ from current environment")

    if "new_zone" in rotation:
        new_zone = rotation["new_zone"]
        if not isinstance(new_zone, str) or not SLUG.fullmatch(new_zone):
            fail(f"{label} new_zone is invalid")

print(json.dumps(plan))
PY
)"
plan_id="$(jq -r '.id // "unnamed"' <<< "$plan_json")"
min_active="$(jq -r '.min_active // 1' <<< "$plan_json")"
total="$(jq -r '.rotations | length' <<< "$plan_json")"

if (( DRY_RUN )); then
  echo "plan id=${plan_id}  rotations=${total}  min_active=${min_active}"
  jq -r '.rotations | to_entries[] | "  \(.key+1)/'"$total"' \(.value.current) → ENV=\(.value.new_env) zone=\(.value.new_zone // "(same)")"' \
    <<< "$plan_json"
  exit 0
fi

STATE="${STATE_DIR}/fleet-rotate-${plan_id}.json"
mkdir -p "$STATE_DIR"
state_dir_resolved="$(cd "$STATE_DIR" && pwd -P)"
state_parent_resolved="$(cd "$(dirname "$STATE")" && pwd -P)"
if [[ "$state_parent_resolved" != "$state_dir_resolved" ]]; then
  echo "refuse: fleet rotation state path escapes state directory" >&2
  exit 1
fi
if [[ -L "$STATE" ]]; then
  echo "refuse: fleet rotation state file is a symlink: $STATE" >&2
  exit 1
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
    local ip
    ip="$(PROVIDER="$prov" ENV="${pair#*:}" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw server_ipv4 2>/dev/null || true)"
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
