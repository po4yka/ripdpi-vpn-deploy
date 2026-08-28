# Runbook — disaster recovery / restore

The architecture targets **15–30 minute restore** from a clean operator
workstation back to a fully functional VPN node. Two paths.

## What you need

- The repo (git clone — public).
- The encrypted SOPS secrets file (`~/.config/vpn-provision/prod.secrets.sops.yaml`).
- Your age private key (`~/.config/vpn-provision/age.key`).
- The Terraform state file for the chosen provider and `ENV` (or willingness to import an existing VPS through `scripts/terraform-env.sh`). `prod` retains Terraform's legacy `default` workspace; other environments use same-named workspaces.
- Optional: a recent restic snapshot from the old VPS, if you want to
  restore configs verbatim instead of re-rendering from secrets.

## Path A — full rebuild from scratch (recommended)

This is the path the architecture is designed for. Don't restore configs;
rebuild them deterministically from secrets and templates.

```bash
# 1. Clone the repo on a clean operator workstation
git clone <repo> ~/GitRep/ripdpi-vpn-deploy
cd ~/GitRep/ripdpi-vpn-deploy

# 2. Restore your age key + SOPS file
mkdir -p ~/.config/vpn-provision
# (copy from your encrypted backup / hardware key / 1Password)

# 3. Provision a fresh VPS — possibly in a different ASN if the old one burned
$EDITOR terraform/providers/upcloud/environments/prod.tfvars
make init plan apply inventory wait

# 4. Deploy
make decrypt
make dry-run
make deploy
make verify
make clean
```

You're done. The new VPS has identical service surface to the old one
(same Xray version, same nginx config shape, same Hysteria policy, same
AWG peers), generated from the same secrets file. Clients reconnect with
their existing URIs (which encode UUIDs/passwords, not IPs — assuming
you used DNS or floating IP).

If clients used bare IP, reissue URIs with `scripts/new-client.sh
--emit-uri <name>` against each client name.

## Path B — restore from restic snapshot

Use only when (a) you have a recent restic backup, (b) you trust the
secrets at the time of the snapshot, and (c) you want to come back up
faster than path A. Note: secrets in the restic snapshot are server-side
artifacts (rendered configs); the canonical source is still the SOPS
file.

```bash
# 1. Provision a fresh VPS
$EDITOR terraform/providers/upcloud/environments/prod.tfvars
make init plan apply inventory wait

# 2. Decrypt secrets before the first playbook; the backup role needs the
#    restic password and site.yml rejects a missing VPN_SECRETS_FILE.
make decrypt

# 3. Push baseline + firewall + backup role only. The make target passes its
#    runtime secrets path as VPN_SECRETS_FILE and writes /etc/restic/password.
ANSIBLE_TAGS="baseline,firewall,backup" make deploy

# 4. Copy restic repo from old backup target — this depends on where you sync
#    restic. Local-only repo means SCP from a forensic snapshot of the old
#    disk. Operators with remote restic targets (S3, BorgBase, etc.) point
#    the new VPS at the same target.

# 5. Restore configs
ssh deploy@<new-vps>
sudo restic -r /var/backups/vpn-restic --password-file /etc/restic/password \
    restore latest --target /

# 6. Reconcile with Ansible (may show drift — investigate before accepting)
make dry-run

# 7. If drift is acceptable / expected, deploy to overwrite restored files
#    with template-rendered ones from current secrets:
make deploy
make verify
make clean
```

Do not hand-repair a snowflake server. Path A is the default. Path B
exists for the "I need to be live in 15 minutes and have a known-good
restic snapshot" case.

## Configure an existing offsite replica without running backup

Use the dedicated command on an already provisioned node. Full `make deploy`,
including a backup tag selection, can converge other roles and start persistent
timers; it is not a configuration-only operation.

The production owner must hold an exclusive maintenance window, record the
previous timer states, persistently disable and stop both backup timers, and let any active backup or
restore finish. Both services and timers must be inactive with no pending jobs.
Do not overlap this window with another deploy or a privileged manual backup.
The command checks that state but never stops, masks, restarts, or enables units.
It requires `UnitFileState=disabled` for both timers so reboot cannot trigger
the canonical schedules during recovery. It is not a multi-file power-loss
atomicity guarantee. Incomplete persistent recovery bundles also block a new
configuration after reboot removes the runtime lock.

Prepare the approved `backup.remote` settings in the canonical encrypted SOPS
document and materialize them with `make decrypt`. Keep the existing restic
password: configuration compares it privately with `/etc/restic/password`, and
never initializes the repository or replaces that password.
Before any lock/package/configuration writes, the installed restic also reads
the local configuration with `--no-cache --no-lock ... cat config`, explicit
repository/password paths, and a 15-second timeout. Output is captured and
discarded. This verifies configuration decryption, not integrity or restoration.

```bash
# Clean committed checkout; exact inventory alias, not a group or pattern.
make backup-configure ANSIBLE_LIMIT=node
```

Invoke this as the only Make goal. Its alias and explicitly supplied secret or
extra-vars paths are literal data, including `$` and quotes; repository-defined
default paths still resolve normally. This is not a sandbox for operator-written
Makefiles or `make --eval`.

The controller derives Git cleanliness/provenance under a controlled environment,
validates one immutable private inventory snapshot, and invokes Ansible with only
that selected alias. SSH uses the selected private key and pinned identity from
`~/.ssh/known_hosts`, without SSH config, agents, multiplexing or proxy inheritance.
Approved `ansible_host`/`ansible_port` extra-vars change transport while retaining
the selected host-key identity. Git routing and Ansible execution/plugin/callback
environment overrides are not forwarded; automatic vars plugins are disabled.

**Configuration contract:** tracked AWG role defaults (data only), `all.yml`,
`vpn.yml`, selected cohort files in Ansible group order, then SOPS are loaded
explicitly; validated extra-vars retain final precedence. External `host_vars`
and arbitrary inventory backup overrides are not supported by this intent.
The AWG defaults supply the same interface name visible to full-site backup
rendering; they do not import or execute AWG tasks or handlers.

The command runs strict secret/certificate and optional extra-vars validation,
requires the existing canonical `/var/backups/vpn-restic` repository and units,
and installs only rclone when missing (`apt state=present`, no cache refresh or
package upgrades requested). Package installation still has ordinary dpkg
effects; this is not a promise of zero host writes. It stages and validates
`/etc/rclone/rclone.conf` and both backup scripts, then replaces them atomically
per file in config/backup/drill order. It does not invoke backup, prune, sync,
restore, timer handlers, or update the whole-node source manifest.

Any publication or final quiescence-check failure restores all three previous
files, including permissions and prior absence. Prior bytes remain in a private
`/var/lib/vpn-backup/configure-recovery/<invocation>/` bundle. A stale lock or
`rollback-incomplete-keep-timers-stopped` requires owner recovery: **do not resume
timers or remove the lock until all three paths have been verified/repaired**.
Do not print recovery JSON or copy it into reports; it contains old credentials.
Only this invocation's staging is cleaned automatically. An interrupted controller
or killed remote process can leave a private lock/bundle for this same recovery.

On success, the owner separately performs the approved initial copy and isolated
remote restore before restoring the previous timer states. On an ordinary failed
configuration with confirmed rollback, restore those states only after reviewing
the reported failure. Configuration success is not offsite-copy or restore proof;
the restore runner must actually open the remote repository without fallback.
No public destination, shared-key isolation, or provider permissions are invented
by this command. Keep reports and Ansible output free of config contents.
Enabled `ANSIBLE_DEBUG` is refused; accepted false values are normalized to
`ANSIBLE_DEBUG=false` for child processes, including when an inherited Ansible
configuration enables debug. Debug logging bypasses Ansible's `no_log` boundary.

## Backup verification (recurring task)

The `backup` role runs a daily snapshot and a monthly non-destructive restore
drill. The drill restores the exact latest `vpn-stack` snapshot into private
systemd runtime storage, validates the baseline and enabled transport
artifacts, removes the restored secrets, and only then updates its success
marker. When remote sync is enabled, the drill opens that offsite repository
directly and does not fall back to the local copy.

```bash
ssh deploy@<vps>
sudo systemctl list-timers vpn-backup-restore-drill.timer
sudo systemctl start vpn-backup-restore-drill.service
sudo python3 -m json.tool /var/lib/vpn-backup/restore-drill-last-success.json
sudo test ! -e /run/vpn-backup-restore-drill
```

`systemctl start` is the synchronous restore-verification gate and returns
nonzero on a missing or stale snapshot, repository/decryption failure,
missing artifact, malformed restored Xray JSON, or cleanup failure. Inspect a
failure without printing restored file contents:

```bash
sudo systemctl status vpn-backup-restore-drill.service
sudo journalctl -u vpn-backup-restore-drill.service --since today
```

Do not treat an older marker as proof that the latest scheduled run passed;
the marker intentionally preserves the last success when a later drill fails.

## Backup repository leak

If you suspect the restic repository itself is compromised (e.g., the
remote target was breached, or the password leaked):

1. Treat every secret in the snapshots as compromised — the snapshots
   contain rendered configs with REALITY private keys, Hysteria certs,
   AWG private keys.
2. Rotate everything per `RUNBOOK-rotate.md` levels 2–4.
3. Re-init the repo with a new password (see `RUNBOOK-rotate.md` § 4).

## RTO / RPO targets

- **RPO** (data loss tolerance): up to 24 hours (daily restic snapshot).
  Lower if you sync remote more often.
- **RTO** (time to recover): 15–30 minutes for path A on a pre-funded
  provider account. Add provider-account-creation time if you don't have
  a sub-account already.

If your operational target is tighter than 30 minutes RTO, you should be
running multi-VPS already. See `RUNBOOK-add-fallback.md`.
