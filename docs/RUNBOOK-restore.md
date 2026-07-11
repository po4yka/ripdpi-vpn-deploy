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
git clone <repo> ~/GitRep/vpn-deploy
cd ~/GitRep/vpn-deploy

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
