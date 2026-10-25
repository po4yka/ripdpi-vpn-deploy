#!/bin/sh
# Disaster-recovery restore orchestrator. Mirrors docs/how-to/restore.md.
# Note: intentional POSIX /bin/sh shebang — pipefail is a bash extension
# and is not available in POSIX sh. set -eu provides the necessary fail-fast
# behaviour within plain sh; pipelines in this script do not need pipefail
# because none of them discard failure through a pipe.
#
# Usage:
#   scripts/restore.sh --env <name> --provider <name> --path-a [--dry-run]
#   scripts/restore.sh --env <name> --provider <name> --path-b [--dry-run]
#
# Options:
#   --env <name>       Target environment name (e.g. prod)
#   --provider <name>  Cloud provider (default: upcloud)
#   --path-a           Full rebuild from scratch (recommended)
#   --path-b           Restore from restic snapshot
#   --dry-run          Print the procedural steps without touching state
#
# Executable Path A: scripts/restore.sh --manifest <private.json> [--resume]
#                    [--approve <review-digest>]
# The private manifest selects the exact replacement; Path B remains manual.
set -eu

MANIFEST=""
APPROVAL=""
ACTION="run"
ENV=""
PROVIDER="upcloud"
PATH_A=0
PATH_B=0
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --manifest)
      [ $# -ge 2 ] || exit 2
      MANIFEST="$2"; shift 2 ;;
    --approve)
      [ $# -ge 2 ] || exit 2
      APPROVAL="$2"; shift 2 ;;
    --resume) ACTION="resume"; shift ;;
    --env)
      [ $# -ge 2 ] || { printf 'error: --env requires a value\n' >&2; exit 1; }
      ENV="$2"; shift 2 ;;
    --provider)
      [ $# -ge 2 ] || { printf 'error: --provider requires a value\n' >&2; exit 1; }
      PROVIDER="$2"; shift 2 ;;
    --path-a) PATH_A=1; shift ;;
    --path-b) PATH_B=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help)
      sed -n '2,/^set -eu/p' "$0" | sed '$d' >&2
      exit 0 ;;
    *)
      printf 'error: unknown argument: %s\n' "$1" >&2; exit 1 ;;
  esac
done

if [ -n "$MANIFEST" ]; then
  [ "$PATH_B" -eq 0 ] && [ "$DRY_RUN" -eq 0 ] && [ -z "$ENV" ] && [ "$PROVIDER" = "upcloud" ] || {
    printf 'error: manifest execution is exact UpCloud Path A only\n' >&2; exit 2;
  }
  SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
  if [ -n "$APPROVAL" ]; then
    exec python3 "$SCRIPT_DIR/recovery.py" "$ACTION" --manifest "$MANIFEST" --approve "$APPROVAL"
  fi
  exec python3 "$SCRIPT_DIR/recovery.py" "$ACTION" --manifest "$MANIFEST"
fi
[ -z "$APPROVAL" ] && [ "$ACTION" = "run" ] || { printf 'error: --manifest required\n' >&2; exit 2; }
[ -n "$ENV" ] || { printf 'error: --env <name> is required\n' >&2; exit 1; }

case "$ENV" in
  default|*[!A-Za-z0-9-]*|-*)
    printf 'error: invalid environment; default is reserved for prod\n' >&2
    exit 1 ;;
esac
case "$PROVIDER" in
  upcloud|hetzner|vultr|scaleway) ;;
  *) printf 'error: unsupported provider\n' >&2; exit 1 ;;
esac

if [ "$PATH_A" -eq 0 ] && [ "$PATH_B" -eq 0 ]; then
  printf 'error: specify --path-a or --path-b\n' >&2
  exit 1
fi

if [ "$PATH_A" -eq 1 ] && [ "$PATH_B" -eq 1 ]; then
  printf 'error: --path-a and --path-b are mutually exclusive\n' >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Path A — full rebuild from scratch (docs/how-to/restore.md § Path A)
# ---------------------------------------------------------------------------
print_prerequisites() {
  printf '  Follow docs/how-to/restore.md Fresh-node prerequisites and docs/how-to/deploy.md.\n'
  printf '  Select reviewed operator SSH key, provider, environment and exact deploy_alias.\n'
  printf '  Provision with separate ordered goals (PROVIDER=%s ENV=%s):\n' "$PROVIDER" "$ENV"
  printf '          make init\n          make plan\n'
  printf '  Review and authorize the exact saved plan before apply.\n'
  printf '          make apply\n          make inventory\n'
  printf '  Authenticate and pin public SSH identity before first SSH contact.\n'
  printf '          make wait\n'
  printf "          make install-ssh-recovery ANSIBLE_LIMIT=\"\$deploy_alias\" SSH_RECOVERY_EXCLUSIVE_WINDOW=1 SSH_RECOVERY_INVENTORY_SECTION=vpn\n"
  printf '  Prepare the reviewed private bootstrap input and its output handoff path.\n'
  printf "          make bootstrap-tailnet ANSIBLE_LIMIT=\"\$deploy_alias\" TAILNET_BOOTSTRAP_CONFIG=<private-config>\n"
  printf '          TAILNET_HANDOFFS=<confirmed-private-handoff> make inventory\n'
  printf '  Prepare DEPLOY_SSH_CONTEXTS_FILE from observed public and Tailnet sockets.\n'
  printf '          SSH_OWNERSHIP_CONFIG=<private-config> make migrate-ssh-ownership\n'
  printf '  Prepare DEPLOY_PROMOTION_CONFIG_FILE and DEPLOY_SSH_BASELINE_FAILURE_RECEIPTS_FILE.\n'
  printf '  Use exact-alias private mappings; receipt sinks must be fresh and absent.\n'
  printf '  Do not fabricate contexts or create empty mappings.\n'
}

print_convergence() {
  printf '          make decrypt\n          make validate\n'
  printf "          make dry-run ANSIBLE_LIMIT=\"\$deploy_alias\" ANSIBLE_TAGS=\n"
  printf '  Review every changed line before continuing.\n'
  printf "          make deploy ANSIBLE_LIMIT=\"\$deploy_alias\" ANSIBLE_TAGS=\n"
  printf "          make verify ANSIBLE_LIMIT=\"\$deploy_alias\"\n"
  printf "          make source-drift ANSIBLE_LIMIT=\"\$deploy_alias\"\n"
  printf '          make clean\n'
  printf '  Clean plaintext on failure or abandonment; run scoped authenticated client acceptance.\n'
}

print_path_a() {
  printf '[restore dry-run] Path A — full rebuild from scratch\n'
  printf '  Step 1: clone the repo; restore operator age key and encrypted SOPS file.\n'
  print_prerequisites
  print_convergence
  printf '\n[restore dry-run] Path A complete — no state modified\n'
}

print_path_b() {
  printf '[restore dry-run] Path B — restore from restic snapshot\n'
  print_prerequisites
  printf '          make decrypt\n          make validate\n'
  printf "          make dry-run ANSIBLE_LIMIT=\"\$deploy_alias\" ANSIBLE_TAGS=\"baseline,firewall,backup\"\n"
  printf '  Review the selected changes before the first tagged deploy.\n'
  printf "          ANSIBLE_TAGS=\"baseline,firewall,backup\" make deploy ANSIBLE_LIMIT=\"\$deploy_alias\"\n"
  printf '          make clean\n'
  printf '  Make the trusted restic repository available; inspect its selected snapshot.\n'
  printf '  In the pinned exact-node SSH session:\n'
  printf '          sudo restic -r /var/backups/vpn-restic --password-file /etc/restic/password restore latest --target / --exclude /var/lib/hysteria/acme --exclude /etc/hysteria/config.yaml --exclude /etc/systemd/system/hysteria-server.service\n'
  printf '  Root restoration can overwrite SSH/recovery/source authority. Stop and inspect it.\n'
  printf '  Repeat required foundation, bootstrap and ownership admission; refresh private mappings.\n'
  print_convergence
  printf '\n[restore dry-run] Path B complete — no state modified\n'
}

# ---------------------------------------------------------------------------
# Dry-run: print steps and exit.
# ---------------------------------------------------------------------------
if [ "$DRY_RUN" -eq 1 ]; then
  if [ "$PATH_A" -eq 1 ]; then
    print_path_a
  else
    print_path_b
  fi
  exit 0
fi

# ---------------------------------------------------------------------------
# Executable recovery requires a complete immutable private selection.
# ---------------------------------------------------------------------------
printf 'Executable Path A requires --manifest <private.json>.\n' >&2
printf 'Path B root-restic restoration requires the separately reviewed runbook.\n' >&2
exit 2
