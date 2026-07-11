#!/bin/sh
# Disaster-recovery restore orchestrator. Mirrors RUNBOOK-restore.md.
# Intentional POSIX /bin/sh: set -eu is the fail-fast contract, and no pipeline
# in this script discards a command failure.
#
# Usage:
#   scripts/restore.sh --env <name> --provider <name> --path-a --dry-run
#   scripts/restore.sh --env <ci-name> --provider <name> --path-a \
#     --execute-ephemeral --confirm-env <ci-name>
#   scripts/restore.sh --env <name> --provider <name> --path-b --dry-run
#
# Options:
#   --env <name>             Technical environment slug
#   --provider <name>        upcloud, hetzner, or vultr (default: upcloud)
#   --path-a                 Full rebuild from scratch (recommended)
#   --path-b                 Document the manual restic restore path
#   --dry-run                Print procedural steps without touching state
#   --execute-ephemeral      Execute Path A for a ci-* throwaway environment
#   --confirm-env <name>     Exact environment confirmation for execution
set -eu

ENV=""
PROVIDER="upcloud"
PATH_A=0
PATH_B=0
DRY_RUN=0
EXECUTE_EPHEMERAL=0
CONFIRM_ENV=""
REPO_ROOT="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"

die() {
  printf 'error: %s\n' "$1" >&2
  exit 2
}

while [ $# -gt 0 ]; do
  case "$1" in
    --env)
      [ $# -ge 2 ] || die "--env requires a value"
      ENV="$2"; shift 2 ;;
    --provider)
      [ $# -ge 2 ] || die "--provider requires a value"
      PROVIDER="$2"; shift 2 ;;
    --path-a) PATH_A=1; shift ;;
    --path-b) PATH_B=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --execute-ephemeral) EXECUTE_EPHEMERAL=1; shift ;;
    --confirm-env)
      [ $# -ge 2 ] || die "--confirm-env requires a value"
      CONFIRM_ENV="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,/^set -eu/p' "$0" | sed '$d' >&2
      exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[ -n "$ENV" ] || die "--env <name> is required"

case "$PROVIDER" in
  upcloud|hetzner|vultr) ;;
  *) die "unsupported provider" ;;
esac

printf '%s\n' "$ENV" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9-]*$' ||
  die "--env must be a technical slug"

if [ "$PATH_A" -eq 0 ] && [ "$PATH_B" -eq 0 ]; then
  die "specify --path-a or --path-b"
fi
if [ "$PATH_A" -eq 1 ] && [ "$PATH_B" -eq 1 ]; then
  die "--path-a and --path-b are mutually exclusive"
fi
if [ "$DRY_RUN" -eq 1 ] && [ "$EXECUTE_EPHEMERAL" -eq 1 ]; then
  die "--dry-run and --execute-ephemeral are mutually exclusive"
fi
if [ "$DRY_RUN" -eq 0 ] && [ "$EXECUTE_EPHEMERAL" -eq 0 ]; then
  die "choose --dry-run or the guarded --execute-ephemeral Path A spike"
fi

if [ "$EXECUTE_EPHEMERAL" -eq 1 ]; then
  [ "$PATH_A" -eq 1 ] || die "--execute-ephemeral supports Path A only"
  printf '%s\n' "$ENV" | grep -Eq '^ci-[A-Za-z0-9][A-Za-z0-9-]*$' ||
    die "--execute-ephemeral requires a ci-* environment"
  [ -n "$CONFIRM_ENV" ] || die "--confirm-env is required for execution"
  [ "$CONFIRM_ENV" = "$ENV" ] || die "--confirm-env must exactly match --env"
elif [ -n "$CONFIRM_ENV" ]; then
  die "--confirm-env is valid only with --execute-ephemeral"
fi

environment_class() {
  case "$ENV" in
    ci-*) printf 'ephemeral' ;;
    *) printf 'production-shaped' ;;
  esac
}

print_path_a() {
  printf '[restore dry-run] Path A — full rebuild from scratch (%s)\n' "$(environment_class)"
  printf '  ENV=%s  PROVIDER=%s\n\n' "$ENV" "$PROVIDER"
  printf '  Step 1: git clone <repo> and cd into it\n'
  printf '  Step 2: restore age key + SOPS file to the operator config directory\n'
  printf '  Step 3: decrypt and run the pre-deploy secret checks\n'
  printf '          make decrypt\n'
  printf '          make pre-deploy-check\n'
  printf '  Step 4: provision the fresh VPS\n'
  printf '          make init plan apply inventory wait  (PROVIDER=%s ENV=%s)\n' "$PROVIDER" "$ENV"
  printf '  Step 5: dry-run, deploy, verify, and clean local plaintext\n'
  printf '          make dry-run deploy verify clean\n'
  printf '\n[restore dry-run] Path A complete — no state modified\n'
}

print_path_b() {
  printf '[restore dry-run] Path B — manual restic restore (%s)\n' "$(environment_class)"
  printf '  ENV=%s  PROVIDER=%s\n\n' "$ENV" "$PROVIDER"
  printf '  Step 1: provision fresh VPS\n'
  printf '          make init plan apply inventory wait  (PROVIDER=%s ENV=%s)\n' "$PROVIDER" "$ENV"
  printf '  Step 2: decrypt secrets before the first playbook\n'
  printf '          make decrypt\n'
  printf '  Step 3: deploy baseline + firewall + backup role\n'
  printf '          ANSIBLE_TAGS="baseline,firewall,backup" make deploy\n'
  printf '  Step 4: point the new VPS at the restic repository\n'
  printf '  Step 5: restore configs manually on the new VPS\n'
  printf '          sudo restic -r <repository> --password-file <file> restore latest --target /\n'
  printf '  Step 6: reconcile with Ansible using make dry-run\n'
  printf '  Step 7: after reviewing drift, deploy, verify, and clean\n'
  printf '\n[restore dry-run] Path B complete — no state modified\n'
}

if [ "$DRY_RUN" -eq 1 ]; then
  if [ "$PATH_A" -eq 1 ]; then
    print_path_a
  else
    print_path_b
  fi
  exit 0
fi

# Test-only command seam. Production execution uses make; tests pass an
# absolute temporary stub. This is intentionally not exposed as a CLI flag.
RECOVERY_MAKE="${RECOVERY_MAKE:-make}"
APPLY_COMPLETED=0
STEP_NUMBER=0

preserve_ephemeral_on_failure() {
  status=$?
  trap - 0
  if [ "$status" -ne 0 ] && [ "$APPLY_COMPLETED" -eq 1 ]; then
    printf 'warning: recovery failed after apply; the ephemeral node may remain\n' >&2
    printf 'manual cleanup: PROVIDER=%s ENV=%s make destroy\n' "$PROVIDER" "$ENV" >&2
  fi
  exit "$status"
}
trap preserve_ephemeral_on_failure 0

run_make_step() {
  STEP_NUMBER=$((STEP_NUMBER + 1))
  target="$1"
  label="$2"
  printf '[recovery %s/11] %s\n' "$STEP_NUMBER" "$label"
  PROVIDER="$PROVIDER" ENV="$ENV" "$RECOVERY_MAKE" "$target"
  if [ "$target" = "apply" ]; then
    APPLY_COMPLETED=1
  fi
}

cd "$REPO_ROOT"
run_make_step decrypt "decrypt recovery secrets"
run_make_step pre-deploy-check "validate secret and certificate inputs"
run_make_step init "initialize the provider workspace"
run_make_step plan "plan ephemeral infrastructure"
run_make_step apply "apply ephemeral infrastructure"
run_make_step inventory "render inventory"
run_make_step wait "wait for the ephemeral node"
run_make_step dry-run "check the deployment"
run_make_step deploy "deploy Path A services"
run_make_step verify "verify the ephemeral node"

if ! "$REPO_ROOT/scripts/audit-log.sh" append-best-effort \
  --action recovery-path-a-spike \
  --env "$ENV" \
  --provider "$PROVIDER" \
  --note "ephemeral Path A execution spike completed verification"; then
  printf 'warning: recovery audit logging failed; continuing\n' >&2
fi

run_make_step clean "remove local plaintext"
printf '[recovery complete] ephemeral Path A execution spike verified; this is not production recovery proof\n'
