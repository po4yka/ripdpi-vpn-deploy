# role: backup — restic with optional offsite replica

## Design decisions

**restic + optional rclone remote** — restic encrypts the repository and
rclone mirrors its opaque contents to the configured offsite backend. The
restic password remains separate from the SOPS/age recovery key.

**Configuration is a separate intent** — `make backup-configure` selects one
exact host and shares configuration rendering with the normal role, but never
imports repository initialization, password writes, units, or timer handlers.
Only the existing rclone package may be installed. A disabled-timer/inactive-service
window belongs to the operator; the command never creates or releases that window.
The controller isolates inventory/plugins and loads tracked AWG defaults as data,
then all/vpn/cohort vars and SOPS. External host_vars are outside this intent.

**Server only backs up its own state** — `/etc/xray`, `/etc/nginx`,
`/var/lib/<service>/` configs and small data. Not logs (`monitoring` has
retention).

**Backup outcomes are producer evidence** — the backup script atomically
replaces a versioned, root-private marker after local, integrity, and optional
remote stages. It contains only bounded stage results and timestamps; timer
state, snapshot identifiers, restic output, and remote configuration are not
evidence.

## What's done well

- **Pre-restore validation** — `RUNBOOK-restore.md` requires checksum
  verification before any restore touches `/etc/`. The role's restore
  playbook refuses to overwrite if the target file's hash matches the backup
  (idempotent restore).
- **Daily by default; manual trigger via `scripts/`** — no surprise weekend
  backup storms.
- **Monthly restore drill** — restores the exact latest snapshot into a
  private systemd runtime directory, validates critical artifacts, removes
  restored secrets, then atomically publishes a last-success marker.
- **Offsite-first verification** — when remote sync is enabled, the drill
  opens the rclone-backed repository directly and fails instead of falling
  back to the local copy.

## Pitfalls

- **Both recovery secrets matter** — losing either the restic password or all
  SOPS/age recovery shares breaks the complete rebuild path.
- **restic forget policy is destructive** — keep at least 7 daily + 4 weekly.
  Bumping the policy down between deploys silently aged-out older snapshots.
- **Remote store credentials live in SOPS** — never in env on the server.
- **Three-file publication must roll back together** — candidate rclone config
  and both scripts are staged before publication. A publication/postcheck failure
  restores prior bytes, modes, and absence. Incomplete rollback retains the private
  recovery bundle and lock; do not resume timers until the owner repairs it.
  Persistent pending bundles block the next invocation even if reboot erased
  the runtime lock; this is not multi-file power-loss atomicity.
- **The configuration lock does not stop root** — it serializes this entrypoint,
  not manual scripts or full deploys. Keep the owner-exclusive window throughout.
  A configuration result is not remote-copy, restore, or whole-site parity proof.
- **Restore drills run as root but never target live paths** — the service
  needs the root-only password and restored files, so runtime cleanup must
  complete before the success marker is replaced. Claim the target with atomic
  `mkdir` before arming cleanup; pre-existing files, directories, and symlinks
  are never owned by that invocation. Metadata and pending markers use private
  unique temporary files, not predictable paths that may contain prior data.
  Publish with atomic replacement, never a move that accepts a destination
  directory; cleanup failures must leave prior success evidence unchanged.
- **AmneziaWG backup and restore share `amneziawg_config_dir`** — never derive
  a shorter parent path or assume configs live directly under `/etc/amnezia`;
  the drill must validate the same nested directory that the role renders.
