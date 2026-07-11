#!/bin/sh
# Disaster-recovery restore orchestrator. Mirrors RUNBOOK-restore.md.
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
# In real mode the individual make / ansible-playbook / ssh invocations are
# performed interactively. See RUNBOOK-restore.md for the canonical procedure.
#
# TODO(maintainer): real-mode automation beyond dry-run is deferred to a
# future iteration — the runbook remains the source of truth for live
# recovery. Only dry-run is fully automated and tested.
set -eu

ENV=""
PROVIDER="upcloud"
PATH_A=0
PATH_B=0
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
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

[ -n "$ENV" ] || { printf 'error: --env <name> is required\n' >&2; exit 1; }

if [ "$PATH_A" -eq 0 ] && [ "$PATH_B" -eq 0 ]; then
  printf 'error: specify --path-a or --path-b\n' >&2
  exit 1
fi

if [ "$PATH_A" -eq 1 ] && [ "$PATH_B" -eq 1 ]; then
  printf 'error: --path-a and --path-b are mutually exclusive\n' >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Path A — full rebuild from scratch (RUNBOOK-restore.md § Path A)
# ---------------------------------------------------------------------------
print_path_a() {
  printf '[restore dry-run] Path A — full rebuild from scratch\n'
  printf '  ENV=%s  PROVIDER=%s\n\n' "$ENV" "$PROVIDER"
  printf '  Step 1: git clone <repo> and cd into it\n'
  printf '  Step 2: restore age key + SOPS file to ~/.config/vpn-provision/\n'
  printf '          cp <backup>/%s.secrets.sops.yaml ~/.config/vpn-provision/\n' "$ENV"
  printf '          cp <backup>/age.key ~/.config/vpn-provision/\n'
  printf '  Step 3: provision fresh VPS\n'
  printf '          make init plan apply inventory wait  (PROVIDER=%s ENV=%s)\n' "$PROVIDER" "$ENV"
  printf '  Step 4: deploy from secrets\n'
  printf '          make decrypt\n'
  printf '          make dry-run\n'
  printf '          make deploy\n'
  printf '          make verify\n'
  printf '          make clean\n'
  printf '\n[restore dry-run] Path A complete — no state modified\n'
}

# ---------------------------------------------------------------------------
# Path B — restore from restic snapshot (RUNBOOK-restore.md § Path B)
# ---------------------------------------------------------------------------
print_path_b() {
  printf '[restore dry-run] Path B — restore from restic snapshot\n'
  printf '  ENV=%s  PROVIDER=%s\n\n' "$ENV" "$PROVIDER"
  printf '  Step 1: provision fresh VPS\n'
  printf '          make init plan apply inventory wait  (PROVIDER=%s ENV=%s)\n' "$PROVIDER" "$ENV"
  printf '  Step 2: decrypt secrets before the first playbook\n'
  printf '          make decrypt\n'
  printf '  Step 3: deploy baseline + firewall + backup role\n'
  printf '          ANSIBLE_TAGS="baseline,firewall,backup" make deploy\n'
  printf '  Step 4: point new VPS at restic repository (remote target or SCP)\n'
  printf '  Step 5: restore configs on new VPS\n'
  printf '          ssh deploy@<new-vps>\n'
  printf '          sudo restic -r /var/backups/vpn-restic \\\n'
  printf '            --password-file /etc/restic/password restore latest --target /\n'
  printf '  Step 6: reconcile with Ansible\n'
  printf '          make dry-run\n'
  printf '  Step 7: (if drift acceptable) overwrite with template-rendered configs\n'
  printf '          make deploy && make verify && make clean\n'
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
# Real mode: interactive guided execution.
# TODO(maintainer): Automate real-mode steps. The runbook is the SOT for now.
# ---------------------------------------------------------------------------
printf 'restore.sh real mode is not yet automated.\n'
printf 'Follow RUNBOOK-restore.md manually for ENV=%s PROVIDER=%s\n' "$ENV" "$PROVIDER"
if [ "$PATH_A" -eq 1 ]; then
  printf 'Use Path A (full rebuild from scratch).\n'
else
  printf 'Use Path B (restore from restic snapshot).\n'
fi
exit 1
