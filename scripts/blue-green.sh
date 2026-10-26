#!/usr/bin/env bash
# Blue-green replacement orchestrator. Operator-driven (asks for confirmation
# at each pivot point) — automation handles the mechanical parts, the human
# decides when to flip traffic and when to retire the old node.
#
# Required env:
#   BLUE_ENV   the existing live env (e.g. prod)
#   GREEN_ENV  the new env name (e.g. green, prod-2026-05-11)
#   PROVIDER   default: upcloud
#   ANSIBLE_SSH_PRIVATE_KEY_FILE
#   GREEN_SOPS_FILE separate encrypted target authority
#   DEVICE_MIGRATION_PLAN reviewed private migration plan
#   DEVICE_MIGRATION_APPROVAL optional preapproval; otherwise enter the reviewed digest
#
# Optional:
#   BLUE_COHORT existing profile (default: fullstack)
#   GREEN_COHORT replacement profile (default: device-full-tailnet)
#   GREEN_TAILNET_HANDOFF, DEPLOY_SSH_CONTEXTS_FILE: private paths to populate before convergence
#   GREEN_ZONE  override zone for the green node (default: same as blue)
#   DRY_RUN     set to 1 (or pass --dry-run) to print plan without mutating
set -euo pipefail

DRY_RUN="${DRY_RUN-0}"
case "$DRY_RUN" in
  0|1) ;;
  *) echo 'DRY_RUN must be 0 or 1' >&2; exit 1 ;;
esac

# Parse flags before consuming positional env vars so callers can do either
# BLUE_ENV=x GREEN_ENV=y scripts/blue-green.sh --dry-run  or use env vars.
_remaining_args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)        DRY_RUN=1; shift ;;
    --blue-env)       BLUE_ENV="$2"; shift 2 ;;
    --green-env)      GREEN_ENV="$2"; shift 2 ;;
    --provider)       PROVIDER="$2"; shift 2 ;;
    --green-zone)     GREEN_ZONE="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,/^set -euo/p' "$0" | sed '$d' >&2
      exit 0 ;;
    *) _remaining_args+=("$1"); shift ;;
  esac
done

PROVIDER="${PROVIDER:-upcloud}"
BLUE_ENV="${BLUE_ENV:?BLUE_ENV required (env var or --blue-env)}"
GREEN_ENV="${GREEN_ENV:?GREEN_ENV required (env var or --green-env)}"
GREEN_ZONE="${GREEN_ZONE:-}"
BLUE_COHORT="${BLUE_COHORT:-fullstack}"
GREEN_COHORT="${GREEN_COHORT:-device-full-tailnet}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TF_DIR="${REPO_ROOT}/terraform/providers/${PROVIDER}"
SOPS_FILE="${SOPS_FILE:-${HOME}/.config/vpn-provision/${BLUE_ENV}.secrets.sops.yaml}"

for environment in "$BLUE_ENV" "$GREEN_ENV"; do
  if [[ ! "$environment" =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ || "$environment" == "default" ]]; then
    echo 'blue-green requires valid distinct environments; default is reserved for prod' >&2
    exit 1
  fi
done
# prod alone owns the legacy default workspace; all admitted other names map
# directly to themselves, so distinct admitted names have distinct state paths.
if [[ "${BLUE_ENV}" == "${GREEN_ENV}" ]]; then
  echo "BLUE_ENV and GREEN_ENV must differ" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Dry-run mode: print planned sequence, no mutations, exit 0.
# ---------------------------------------------------------------------------
if (( DRY_RUN )); then
  cat <<EOF
[dry-run] blue-green sequence for PROVIDER=${PROVIDER} BLUE_ENV=${BLUE_ENV} GREEN_ENV=${GREEN_ENV}

  1/8  Verify blue health  (sops --decrypt, make verify) — read-only
  2/8  Bootstrap green tfvars if missing  (scripts/new-cohort.sh)
  3/8  terraform plan via workspace wrapper: PROVIDER=${PROVIDER} ENV=${GREEN_ENV} scripts/terraform-env.sh plan -var-file=environments/${GREEN_ENV}.tfvars, then apply after a typed yes
  4/8  Establish pinned SSH + Tailnet ownership; review DEVICE_MIGRATION_PLAN and approve its exact digest; device-migration prepare, then decrypt separate GREEN_SOPS_FILE; make dry-run (--check) and, after a typed yes, deploy for the exact green alias
  5/8  make verify and smoke-test for the exact green alias, then device-migration publish through unchanged subscription URLs
  6/8  Operator origin pivot and explicit per-device receipt/attestation — manual step
  7/8  device-migration ready must pass before drain guidance; retain blue while evidence is incomplete
  8/8  Retain green's provider/environment identity for migrated devices

[dry-run] no terraform apply, no ansible changes, no audit-log writes, no sops mutations
EOF
  exit 0
fi

if [[ -z "${ANSIBLE_SSH_PRIVATE_KEY_FILE:-}" ]]; then
  echo "ANSIBLE_SSH_PRIVATE_KEY_FILE must be set" >&2
  exit 1
fi

# Admit explicit separate authorities before any provider or credential action.
: "${GREEN_SOPS_FILE:?GREEN_SOPS_FILE required; target authority must be separate}"
: "${DEVICE_MIGRATION_PLAN:?DEVICE_MIGRATION_PLAN required}"
if [[ -n "${DEVICE_MIGRATION_APPROVAL:-}" && ! "$DEVICE_MIGRATION_APPROVAL" =~ ^[0-9a-f]{64}$ ]]; then
  echo 'DEVICE_MIGRATION_APPROVAL must be the exact reviewed SHA-256 digest' >&2
  exit 1
fi
if [[ ! -f "$GREEN_SOPS_FILE" || "$SOPS_FILE" -ef "$GREEN_SOPS_FILE" ]]; then
  echo 'blue-green requires an existing separate GREEN_SOPS_FILE' >&2
  exit 1
fi

assert_migration_plan() {
  python3 - "$DEVICE_MIGRATION_PLAN" "$PROVIDER:$BLUE_ENV" "$PROVIDER:$GREEN_ENV" \
    "$BLUE_COHORT" "$GREEN_COHORT" "$SOPS_FILE" "$GREEN_SOPS_FILE" \
    "$REPO_ROOT/ansible/inventory/generated.ini" "${BLUE_ALIAS:-}" "${GREEN_ALIAS:-}" <<'PLAN'
import json, os, stat, sys
from pathlib import Path

def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result

try:
    descriptor = os.open(sys.argv[1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        metadata = os.fstat(stream.fileno())
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                or metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_size > 262144):
            raise ValueError
        plan = json.loads(stream.read(262145), object_pairs_hook=unique)
    for index, name in enumerate(('source', 'target')):
        node = plan[name]
        if (node['host'] != sys.argv[2 + index] or node['cohort'] != sys.argv[4 + index]
                or Path(node['secrets_file']).resolve() != Path(sys.argv[6 + index]).resolve()
                or sys.argv[9 + index] and node['alias'] != sys.argv[9 + index]):
            raise ValueError
    if Path(plan['inventory']).resolve() != Path(sys.argv[8]).resolve():
        raise ValueError
except (OSError, ValueError, TypeError, KeyError, RecursionError):
    sys.exit('blue-green migration plan must match the selected nodes, aliases, cohorts, secrets and inventory')
PLAN
}
assert_migration_plan

run_migration() {
  local action="$1"
  shift
  python3 "$REPO_ROOT/scripts/device-migration.py" "$action" --plan "$DEVICE_MIGRATION_PLAN" "$@"
}

step() { echo; echo "==> $*"; }

run_make() {
  env -u MAKELEVEL -u MAKEFLAGS -u MAKEFILES -u MFLAGS -u GNUMAKEFLAGS -u MAKEOVERRIDES \
    make -C "$REPO_ROOT" "$@"
}

require_vpn_alias() {
  local alias="$1"
  [[ "$alias" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || {
    echo 'blue-green requires an exact inventory alias' >&2
    return 1
  }
  ANSIBLE_CONFIG="$REPO_ROOT/ansible/ansible.cfg" \
    ansible-inventory --inventory "$REPO_ROOT/ansible/inventory/generated.ini" --list | python3 -c '
import json, sys
inventory = json.load(sys.stdin)
seen = set()
def members(group):
    if group in seen:
        return set()
    seen.add(group)
    entry = inventory.get(group, {})
    hosts = set(entry.get("hosts", []))
    for child in entry.get("children", []):
        hosts.update(members(child))
    return hosts
alias = sys.argv[1]
if alias in inventory or alias not in members("vpn"):
    sys.exit("blue-green target is absent or ambiguous in the VPN inventory")
' "$alias"
}

confirm() {
  local prompt="$1"
  read -r -p "$prompt [yes/NO]: " ans
  [[ "$ans" == "yes" ]]
}

# ---------------------------------------------------------------------------
# 1. Pre-flight: blue must be healthy and we must have its secrets decrypted.
# ---------------------------------------------------------------------------
step "1/8  Verify blue health (BLUE_ENV=${BLUE_ENV})"
if [[ ! -f "$SOPS_FILE" ]]; then
  echo "missing $SOPS_FILE" >&2
  exit 1
fi

umask 077
SECRETS_DIR="$(mktemp -d -t vpn-blue-green.XXXXXX)"
SECRETS_FILE="${SECRETS_DIR}/secrets.yaml"
GREEN_SECRETS_FILE="${SECRETS_DIR}/green.yaml"
cleanup_secrets() {
  local file
  for file in "$SECRETS_FILE" "$GREEN_SECRETS_FILE"; do
    if [[ -e "$file" || -L "$file" ]]; then
      shred -u -- "$file" 2>/dev/null || rm -f -- "$file"
    fi
  done
  rmdir "$SECRETS_DIR" 2>/dev/null || true
}
trap cleanup_secrets EXIT
sops --decrypt "$SOPS_FILE" > "$SECRETS_FILE"

BLUE_ALIAS="$(PROVIDER="$PROVIDER" ENV="$BLUE_ENV" "$REPO_ROOT/scripts/terraform-env.sh" output -raw server_hostname)"
require_vpn_alias "$BLUE_ALIAS"
assert_migration_plan
SECRETS_FILE="$SECRETS_FILE" ANSIBLE_LIMIT="$BLUE_ALIAS" \
  ENV="${BLUE_ENV}" PROVIDER="${PROVIDER}" \
  run_make verify
python3 "$REPO_ROOT/scripts/device_migration_inventory.py" check --plan "$DEVICE_MIGRATION_PLAN"

# ---------------------------------------------------------------------------
# 2. Bootstrap green tfvars from blue (if missing)
# ---------------------------------------------------------------------------
GREEN_TFVARS="${TF_DIR}/environments/${GREEN_ENV}.tfvars"
if [[ ! -f "$GREEN_TFVARS" ]]; then
  step "2/8  Generate green tfvars from blue"
  PROVIDER="$PROVIDER" SOURCE_ENV="$BLUE_ENV" \
    "${REPO_ROOT}/scripts/new-cohort.sh" "$GREEN_ENV" ${GREEN_ZONE:+"$GREEN_ZONE"}
  echo
  echo "Edit $GREEN_TFVARS now if you need to tweak server_name, plan, image, or zone."
  read -r -p "Press Enter when ready, or Ctrl-C to abort: " _
fi

# Hetzner keeps one SSH key per fingerprint in a project and every root creates
# its own key, so the green apply would fail on blue's key. Refuse before plan.
if [[ "$PROVIDER" == hetzner ]]; then
  python3 - "${TF_DIR}/environments/${BLUE_ENV}.tfvars" "$GREEN_TFVARS" <<'PY'
import re
import sys

pattern = re.compile(r'^\s*admin_ssh_public_key\s*=\s*"([^"]*)"', re.MULTILINE)
keys = []
for path in sys.argv[1:]:
    try:
        match = pattern.search(open(path, encoding="utf-8").read())
    except OSError:
        match = None
    # Key type and body; a comment does not change the fingerprint.
    keys.append(" ".join(match.group(1).split()[:2]) if match else None)
if keys[0] is not None and keys[0] == keys[1]:
    sys.exit("Hetzner keeps one SSH key per fingerprint in a project: set a separate "
             f"admin_ssh_public_key (a new operator key pair) in {sys.argv[2]}")
PY
fi

# ---------------------------------------------------------------------------
# 3. Provision green
# ---------------------------------------------------------------------------
step "3/8  Provision green (ENV=${GREEN_ENV})"
: "${GREEN_TAILNET_HANDOFF:?set the private GREEN_TAILNET_HANDOFF output path before provisioning}"
: "${DEPLOY_SSH_CONTEXTS_FILE:?set the private DEPLOY_SSH_CONTEXTS_FILE path before provisioning}"
for goal in init plan; do
  SOPS_FILE="$GREEN_SOPS_FILE" ENV="$GREEN_ENV" PROVIDER="$PROVIDER" run_make "$goal"
done
if ! confirm "Review the green plan above. Apply it?"; then
  echo "Aborting before apply; no green resources were changed." >&2
  exit 1
fi
SOPS_FILE="$GREEN_SOPS_FILE" ENV="$GREEN_ENV" PROVIDER="$PROVIDER" run_make apply

# ---------------------------------------------------------------------------
# 4. Render multi-host inventory and deploy green
# ---------------------------------------------------------------------------
step "4/8  Establish authenticated green ownership, then render and deploy"

GREEN_ALIAS="$(PROVIDER="$PROVIDER" ENV="$GREEN_ENV" "$REPO_ROOT/scripts/terraform-env.sh" output -raw server_hostname)"
[[ "$GREEN_ALIAS" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || exit 1
cat <<'EOF'
Before any green SSH contact, obtain its public host key through the provider's
authenticated console or another authenticated channel and verify its identity.
Pin the verified public endpoint in standard OpenSSH known_hosts, and prepare
the private pinned known-hosts file required by the bootstrap controller.
Do not treat ssh-keyscan output as identity proof.
EOF
read -r -p "Press Enter after the public SSH identity has been authenticated and pinned: " _
GREEN_PUBLIC_IP="$(PROVIDER="$PROVIDER" ENV="$GREEN_ENV" "$REPO_ROOT/scripts/terraform-env.sh" output -raw server_ipv4)"
GREEN_SSH_PORT="$(PROVIDER="$PROVIDER" ENV="$GREEN_ENV" "$REPO_ROOT/scripts/terraform-env.sh" output -raw ssh_port)"
[[ "$GREEN_SSH_PORT" =~ ^[1-9][0-9]*$ ]] && (( GREEN_SSH_PORT <= 65535 )) || exit 1
GREEN_HOST_KEY_ALIAS="$GREEN_PUBLIC_IP"
if [[ "$GREEN_SSH_PORT" != 22 ]]; then
  GREEN_HOST_KEY_ALIAS="[${GREEN_PUBLIC_IP}]:${GREEN_SSH_PORT}"
fi
ssh-keygen -F "$GREEN_HOST_KEY_ALIAS" -f "${HOME}/.ssh/known_hosts" >/dev/null || {
  echo 'verified green public SSH pin is missing from standard known_hosts' >&2
  exit 1
}
HOSTS="${PROVIDER}:${BLUE_ENV},${PROVIDER}:${GREEN_ENV}" \
COHORTS="${BLUE_COHORT},${GREEN_COHORT}" \
TAILNET_HANDOFFS="${BLUE_TAILNET_HANDOFF:--},-" \
  python3 "$REPO_ROOT/scripts/device_migration_inventory.py" render --plan "$DEVICE_MIGRATION_PLAN"
require_vpn_alias "$GREEN_ALIAS"
SOPS_FILE="$GREEN_SOPS_FILE" ANSIBLE_LIMIT="$GREEN_ALIAS" ENV="$GREEN_ENV" PROVIDER="$PROVIDER" \
  run_make wait
cat <<EOF
Before convergence, prepare the new node's pinned public and Tailnet SSH paths:
  make install-ssh-recovery ANSIBLE_LIMIT="$GREEN_ALIAS" SSH_RECOVERY_EXCLUSIVE_WINDOW=1 SSH_RECOVERY_INVENTORY_SECTION=vpn
  make bootstrap-tailnet
  make migrate-ssh-ownership
Use the exact green alias and the private inputs documented in docs/how-to/tailnet-management.md.
Set GREEN_TAILNET_HANDOFF to the confirmed handoff path and
DEPLOY_SSH_CONTEXTS_FILE to the prepared socket-context file before starting
this script. Those paths may be populated during this pause.
Before rendering any Vultr secondary-IP guest, also pin its public SSH endpoint
in the operator's standard OpenSSH known_hosts using an authenticated source.
Inventory validation refuses unknown or changed keys; never use ssh-keyscan as
identity proof. The deployment controller performs readiness over pinned SSH.
EOF
read -r -p "Press Enter after green SSH ownership is established: " _
: "${GREEN_TAILNET_HANDOFF:?GREEN_TAILNET_HANDOFF required}"
: "${DEPLOY_SSH_CONTEXTS_FILE:?DEPLOY_SSH_CONTEXTS_FILE required}"
HOSTS="${PROVIDER}:${BLUE_ENV},${PROVIDER}:${GREEN_ENV}" \
COHORTS="${BLUE_COHORT},${GREEN_COHORT}" \
TAILNET_HANDOFFS="${BLUE_TAILNET_HANDOFF:--},${GREEN_TAILNET_HANDOFF}" \
  python3 "$REPO_ROOT/scripts/device_migration_inventory.py" render --plan "$DEVICE_MIGRATION_PLAN"
require_vpn_alias "$GREEN_ALIAS"
assert_migration_plan
run_migration plan
if [[ -z "${DEVICE_MIGRATION_APPROVAL:-}" ]]; then
  read -r -p "Review the device migration above; enter its exact approval digest: " DEVICE_MIGRATION_APPROVAL
fi
[[ "$DEVICE_MIGRATION_APPROVAL" =~ ^[0-9a-f]{64}$ ]] || {
  echo 'device migration requires the exact reviewed approval digest' >&2
  exit 1
}
run_migration prepare --approve "$DEVICE_MIGRATION_APPROVAL"
# Preparation committed target credentials. Decrypt that exact authority only now.
sops --decrypt "$GREEN_SOPS_FILE" > "$GREEN_SECRETS_FILE"
SECRETS_FILE="$GREEN_SECRETS_FILE" SOPS_FILE="$GREEN_SOPS_FILE" ANSIBLE_LIMIT="$GREEN_ALIAS" \
  ENV="$GREEN_ENV" PROVIDER="$PROVIDER" run_make dry-run
if ! confirm "Review the green dry-run above. Deploy it?"; then
  echo "Aborting before deploy. Green is provisioned; clean up later with: ENV=${GREEN_ENV} make destroy" >&2
  exit 1
fi
SECRETS_FILE="$GREEN_SECRETS_FILE" SOPS_FILE="$GREEN_SOPS_FILE" ANSIBLE_LIMIT="$GREEN_ALIAS" \
  ENV="$GREEN_ENV" PROVIDER="$PROVIDER" run_make deploy

# ---------------------------------------------------------------------------
# 5. Verify + smoke test green
# ---------------------------------------------------------------------------
step "5/8  Verify + smoke-test green"
for goal in verify smoke-test; do
  SECRETS_FILE="$GREEN_SECRETS_FILE" SOPS_FILE="$GREEN_SOPS_FILE" ANSIBLE_LIMIT="$GREEN_ALIAS" \
    ENV="$GREEN_ENV" PROVIDER="$PROVIDER" run_make "$goal"
done
run_migration publish

# ---------------------------------------------------------------------------
# 6. Operator pivot — flip clients / DNS / floating IP
# ---------------------------------------------------------------------------
step "6/8  Operator pivot"
GREEN_IP="$(PROVIDER="$PROVIDER" ENV="$GREEN_ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw server_ipv4)"
cat <<EOF

Green node is ready. Its public IPv4 is: ${GREEN_IP}

Operator action required:
  - Preserve the reviewed subscription origin when moving its publisher: pivot
    its DNS or floating/reserved IP only after both publishers serve the grants.
  - Refresh each device through its unchanged subscription URL and test its exact
    green path. Import its receipt with device-migration receipt, or record an
    explicit per-device attestation with device-migration attest.

Publication and generic server health do not count as per-device path evidence.
Keep blue while any device remains unverified.

EOF
if ! confirm "Has traffic been swung to green and verified from a real client?"; then
  echo "Handover incomplete. Retain both blue and green; devices may already use green."
  echo "Resume device-migration receipt/attest and ready, or explicitly review device-migration rollback"
  echo "before considering green retirement. Keep both environments and their current identities."
  exit 1
fi

# ---------------------------------------------------------------------------
# 7. Drain — keep blue alive
# ---------------------------------------------------------------------------
run_migration ready
step "7/8  Drain blue (all migration participants accepted)"
echo "Convention: keep blue alive for 24-72 hours so cached client sessions"
echo "fail over to green. Re-run the next step when you're ready to retire blue."
echo
echo "When ready to destroy blue, run:"
echo "    ENV=${BLUE_ENV} make destroy"

# ---------------------------------------------------------------------------
# 8. Retain the identity consumed by migrated devices
# ---------------------------------------------------------------------------
step "8/8  Retain ENV=${GREEN_ENV} as the migrated authority"
echo "Keep operating under PROVIDER=${PROVIDER} ENV=${GREEN_ENV}."
echo "Device hosts and delivery sources now depend on that identity."
echo "Any future environment reassignment requires a separately reviewed migration."
echo
echo "Blue-green orchestration done."
