# role: backup — restic with optional offsite replica

## Design decisions

**restic + optional rclone remote** — restic encrypts the repository and
rclone mirrors its opaque contents to the configured offsite backend. The
restic password remains separate from the SOPS/age recovery key.

**Server only backs up its own state** — `/etc/xray`, `/etc/nginx`,
`/var/lib/<service>/` configs and small data. Not logs (`monitoring` has
retention).

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
- **Restore drills run as root but never target live paths** — the service
  needs the root-only password and restored files, so runtime cleanup must
  complete before the success marker is replaced.
- **AmneziaWG backup and restore share `amneziawg_config_dir`** — never derive
  a shorter parent path or assume configs live directly under `/etc/amnezia`;
  the drill must validate the same nested directory that the role renders.
