# Runbook — disaster recovery / restore

> **Status:** Current · **Type:** how-to · **Tier:** CORE · **Reviewed:** 2026-10-21

## Purpose and scope

Recover a working node after host loss, either by rebuilding from git plus
the encrypted secrets (the designed path) or by restoring the restic
snapshot, inside the 15 to 30 minute target.

The architecture targets **15–30 minute restore** from a clean operator
workstation back to a fully functional VPN node. Two paths.

## Preconditions

- The items under [What you need](#what-you-need): the age key or its Shamir shares, the encrypted secrets file, provider credentials and the restic repository access.
- A fresh node meets [the fresh-node prerequisites](#fresh-node-prerequisites) before any deployment step.
- The operator kit catalogue in [the local operator kit](local-operator-kit.md) says where each item lives.

## Authorization

Every target below that uses cloud credentials, inventory, SSH or decrypted secrets needs the operator's authorization for this environment, target and plan before it runs ([decision boundaries](../../AGENTS.md#decision-boundaries)). A reviewable plan or dry-run precedes every mutation. Provisioning a replacement node and deploying to it are separate authorizations; a restore request covers both only when it says so.

## What you need

- The repo (git clone — public).
- The encrypted SOPS secrets file (`~/.config/vpn-provision/prod.secrets.sops.yaml`).
- Your age private key (`~/.config/vpn-provision/age.key`).
- The Terraform state file for the chosen provider and `ENV` (or willingness to import an existing VPS through `scripts/terraform-env.sh`). `prod` retains Terraform's legacy `default` workspace; other environments use same-named workspaces.
- Optional: a recent restic snapshot from the old VPS, if you want to
  restore configs verbatim instead of re-rendering from secrets.

## Fresh-node prerequisites

Both paths require the current [deployment prerequisites](deploy.md#ordinary-re-deploy-recipe).
Restore the operator key and encrypted SOPS source first. Select the exact
provider, environment, reviewed SSH key and inventory alias. `default` is reserved;
use `prod` for legacy production state. Review the existing state and plan before
provisioning a replacement. Do not apply over the old node by mistake.

Run each dependent Make goal separately. An inherited parallel Make setting must
not start provisioning, inventory generation and deployment at the same time.

```bash
export PROVIDER=upcloud ENV=prod
export ANSIBLE_SSH_PRIVATE_KEY_FILE="$HOME/.ssh/vpn_deploy" # Reviewed node key.
make init
make plan
# Review the saved plan and obtain authorization for its exact resource changes.
make apply
make inventory
# Authenticate the new public host key through the provider console or another
# authenticated channel. Pin it in known_hosts before the first SSH contact.
# ssh-keyscan output alone is not identity proof.
make wait
```

Before the first ordinary `dry-run` or `deploy`, complete these steps for the
exact alias. The example paths refer to reviewed private inputs, not generated
empty files. Keep JSON inputs at `0600` under an owner-only directory. A fresh
node has no accepted Tailnet handoff or socket contexts until bootstrap succeeds.

```bash
deploy_alias='<exact-inventory-alias>'
make install-ssh-recovery ANSIBLE_LIMIT="$deploy_alias" SSH_RECOVERY_EXCLUSIVE_WINDOW=1
# Prepare the one-node private config as documented in tailnet-management.md.
make bootstrap-tailnet ANSIBLE_LIMIT="$deploy_alias" \
  TAILNET_BOOTSTRAP_CONFIG="$HOME/.config/vpn-provision/bootstrap-tailnet.json"
# Use the handoff actually produced by successful bootstrap.
TAILNET_HANDOFFS="$HOME/.config/vpn-provision/tailnet-handoff.json" make inventory
export DEPLOY_SSH_CONTEXTS_FILE="$HOME/.config/vpn-provision/ssh-contexts.json"
# Assemble this exact-alias mapping from observed public and Tailnet sockets.
# Prepare the ownership config with the current source identity and contexts path.
SSH_OWNERSHIP_CONFIG="$HOME/.config/vpn-provision/ssh-ownership.json" make migrate-ssh-ownership
export DEPLOY_PROMOTION_CONFIG_FILE="$HOME/.config/vpn-provision/promotion-configs.json"
export DEPLOY_SSH_BASELINE_FAILURE_RECEIPTS_FILE="$HOME/.config/vpn-provision/ssh-baseline-failure-receipts.json"
unset TAILSCALE_AUTH_KEY
```

Follow [one-node bootstrap](tailnet-management.md#bootstrap-one-node) for its
private inputs and output path. Follow [the deployment input table](deploy.md)
for both exact-alias mappings. Promotion configuration must bind this node and
source; each failure-receipt sink must be distinct and absent. Do not fabricate
socket contexts or use empty mappings. Before every retry, review retained
failure state and select fresh failure-receipt paths.

## Path A — full rebuild from scratch (recommended)

For one UpCloud replacement with a surviving dedicated publisher, use
[executable recovery](executable-recovery.md). It preserves private phase intent,
reconciles interrupted provider actions and resumes through device migration
acceptance. The manual procedure below covers other admitted recovery scopes.

Rebuild configurations from current secrets and templates. Clone the repository,
restore the operator key and encrypted secrets, then complete **Fresh-node
prerequisites** above. Use the clean reviewed source revision required by the
controller.

```bash
(
set -e
trap 'make clean' EXIT
make decrypt
make validate
make dry-run ANSIBLE_LIMIT="$deploy_alias" ANSIBLE_TAGS=
# Stop and review every change before the next command.
make deploy ANSIBLE_LIMIT="$deploy_alias" ANSIBLE_TAGS=
make verify ANSIBLE_LIMIT="$deploy_alias"
make source-drift ANSIBLE_LIMIT="$deploy_alias"
)
```

Run `make clean` when abandoning recovery, including after an interrupted shell.
Successful convergence is source evidence. Complete the selected authenticated
client checks in [deployment acceptance](deploy.md#acceptance-scope-and-completion)
before declaring service restored. Existing clients require the correct endpoint;
DNS or floating-IP changes are separate authorized actions.

If clients used bare IP, regenerate selected client exports with the canonical
emitter and updated endpoint. New device issuance with `scripts/new-client.sh
--emit-uri <name>` requires `OUTPUT=<new private recipient file>`; issuance
refuses an existing client identity and does not serve as read-only recovery.

## Path B — restore from restic snapshot

Use a trusted recent snapshot only when its rendered server artifacts are needed.
The encrypted SOPS source remains authoritative. Complete **Fresh-node
prerequisites**, including all three private deployment mappings, before the
first tagged deploy. Tag selection does not bypass controller admission.

```bash
(
set -e
trap 'make clean' EXIT
make decrypt
make validate
make dry-run ANSIBLE_LIMIT="$deploy_alias" ANSIBLE_TAGS="baseline,firewall,backup"
# Review the baseline, firewall and backup changes before continuing.
ANSIBLE_TAGS="baseline,firewall,backup" make deploy ANSIBLE_LIMIT="$deploy_alias"
)
```

Make the approved restic repository available on the replacement node. A
local-only repository requires a trusted disk snapshot; a remote repository
requires its reviewed credentials and target. Open the pinned exact-node SSH
session with the selected operator key. On that node, inspect the selected
snapshot before restoring its server artifacts:

```bash
sudo restic -r /var/backups/vpn-restic --password-file /etc/restic/password snapshots
sudo restic -r /var/backups/vpn-restic --password-file /etc/restic/password \
    restore latest --target / \
    --exclude /var/lib/hysteria/acme \
    --exclude /etc/hysteria/config.yaml \
    --exclude /etc/systemd/system/hysteria-server.service
```

Native Hysteria ACME requires separate fresh-node admission. Never restore its
cache or unit directly into the replacement host. Select a full snapshot ID,
restore that exact snapshot into a root-owned mode-0700 directory under
`/run/vpn-acme-restore-<8-to-32-alphanumeric-characters>`, and retain that ID.
The live `/var/lib/hysteria` parent must be root-owned mode 0750; the cache
must be an empty, separate mode-0700 directory owned by the current Hysteria
user and group. The Hysteria service must not exist yet.

For the initial full dry-run and deploy, pass a same-owner mode-0600
`ANSIBLE_EXTRA_VARS_FILE` with only `hysteria_acme_restore_root` and
`hysteria_acme_restore_snapshot_id`. Use the selected private runtime path and
the full 64-character snapshot ID. The role checks the exact production CA,
domain, certificate/key pair, metadata and account, then runs its pinned native
server and authenticated client in an isolated network. The original ACME
configuration uses a disposable cache copy. Only a successful proof permits
atomic publication of the normalized cache with current service ownership.
An interrupted publication resumes through its retained private journal.
An accepted node or a foreign/nonempty cache refuses fresh recovery.

After successful deploy, remove these one-time overrides and the private
scratch directory. Ordinary convergence does not copy or change cache contents.
A certificate already near its renewal window cannot pass disconnected warm
admission; inspect it before choosing fresh online issuance instead. Warm
admission proves immediate authenticated service. Only a separate online
renewal proves that the CA still accepts the restored account key.

A root restore can overwrite recovery files, SSH policy and deployment source
metadata. Stop before ordinary deployment: inspect those changes, reinstall the
current recovery foundation if its generation changed, and repeat the bootstrap,
ownership and fresh dual-path admission required by **Fresh-node prerequisites**.
Retain the observed handoff and refresh the three private mappings; restored
files are not fresh proof. Do not delete a failure receipt to make a retry pass.

After that admission succeeds, use the full **Path A** convergence block to
compare and reconcile restored files with current source. Review unexpected drift
before deploy, then run scoped authenticated client acceptance. Path B does not
make a fresh node ready by copying configuration files alone.

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
2. Rotate everything per `rotate.md` levels 2–4.
3. Re-init the repo with a new password (see `rotate.md` § 4).

## RTO / RPO targets

- **RPO** (data loss tolerance): up to 24 hours (daily restic snapshot).
  Lower if you sync remote more often.
- **RTO** (time to recover): 15–30 minutes for path A on a pre-funded
  provider account. Add provider-account-creation time if you don't have
  a sub-account already.

If your operational target is tighter than 30 minutes RTO, you should be
running multi-VPS already. See `add-fallback.md`.

## Verification

[Backup verification](#backup-verification-recurring-task) proves the
restored node serves every profile; `make verify`, `make security-verify` and
`make smoke-test` complete the acceptance. Compare the observed time with the
[RTO and RPO targets](#rto--rpo-targets).

## Rollback

Path A is the fallback for Path B: when a snapshot restore fails or looks
inconsistent, rebuild from git plus secrets. A suspected repository leak is
handled under [Backup repository leak](#backup-repository-leak) before any
restore.

## Evidence to record

Which path was used, the snapshot identity for Path B, the observed restore
time, the verify results and any prerequisite that was missing from the
operator kit, so the kit catalogue can be corrected.
