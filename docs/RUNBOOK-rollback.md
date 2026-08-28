# Runbook — rollback

Three rollback levels. Pick the smallest one that fixes the failure.

## Level 1 — config rollback (handler rescue, automatic)

The `xray` role's `Restart xray` handler has `block:` / `rescue:`. If a
new config fails `xray run -test -config` or doesn't come up active
within 5 retries × 2s, the handler:

1. Restores `/etc/xray/config.json.prev`
2. Restarts xray
3. Fails the play

You'll see `Xray restart failed; previous config was restored if
available.` in the Ansible output. The host is back on the previous
config. Investigate the bad template, fix it, re-deploy.

If automatic rescue didn't fire (e.g., the bad change was outside the
xray template — say nftables), trigger the manual playbook:

```bash
ansible-playbook ansible/playbooks/rollback-config.yml
```

It restores `/etc/xray/config.json.prev` → validates → restarts.

## Level 2 — binary rollback

Use when a new Xray pinned version misbehaves (slow, leaks, crashes).
Previous releases stay in `/opt/xray/releases/<version>/`; only the
`current` symlink points at the active one.

```bash
# Find the previous release
ssh deploy@<vps> ls /opt/xray/releases

# Roll the symlink back
make rollback-xray ROLLBACK_XRAY_VERSION=v26.3.27
```

The playbook accepts only a pinned `vMAJOR.MINOR.PATCH` (or unprefixed)
release with a regular executable binary and refuses the current release.
It validates the existing config with the target binary **before** changing
the runtime link, then restarts and verifies `is-active`. Check mode also
runs this read-only binary validation; it does not change the link or restart.

To make the rollback permanent, also update `xray.version` and
`xray.linux_*_sha256` in secrets back to the rolled-back version, so
future `make deploy` runs don't re-pull the broken release.

## Level 3 — blue-green VPS replacement

Use when the host itself is the problem: IP burned, kernel panic loop,
hypervisor outage, or you suspect compromise.

```bash
# Orchestrated form (recommended):
PROVIDER=upcloud BLUE_ENV=prod GREEN_ENV=green-2026-05 \
  ANSIBLE_SSH_PRIVATE_KEY_FILE=~/.ssh/vpn_deploy \
  make blue-green GREEN_ENV=green-2026-05
#
# scripts/blue-green.sh walks 8 phases (verify blue → bootstrap green
# tfvars → provision → multi-host inventory → deploy + verify + smoke-test
# → operator pivot → drain → optional retire). It pauses at the operator
# pivot step so you flip DNS / floating IP yourself.
#
# Manual form (for finer control):
# 1. Bring up a green node alongside blue. Use a different server_name in tfvars
#    (e.g., vpn-prod-fi2 instead of vpn-prod-fi1) so they coexist. You'll have
#    to drop or temporarily relax `prevent_destroy` on blue if you want
#    Terraform to manage both — easiest is a separate ENV value:
ENV=green make plan apply inventory wait dry-run deploy verify

# 2. Test green with a real client.

# 3. Switch DNS / floating IP / subscription URL to green. If clients use bare
#    IP, reissue subscriptions — they'll need the new IP anyway.

# 4. Drain blue: keep it alive 24-72 hours so any cached client connections
#    can fail over to green's URI on next reconnect.

# 5. Destroy blue:
PROVIDER=upcloud ENV=prod make destroy
# (You'll need to remove `prevent_destroy = true` first — by design.)
```

If you have a UpCloud floating IP attached to blue, transfer it to green
in the UpCloud console (or via API), and the IP-bound clients reconnect
without reissuing.

## SSH ownership recovery foundation

The separate installer publishes recovery code and persistent systemd units;
it does **not** migrate SSH configuration or change listeners, keys, firewall
rules or Tailnet policy. From a clean tested checkout, during an exclusive
single-node maintenance window:

```bash
make install-ssh-recovery ANSIBLE_LIMIT=<exact-inventory-alias> \
  SSH_RECOVERY_EXCLUSIVE_WINDOW=1
```

The existing generated inventory and pinned known-hosts file are required.
Optional `SSH_RECOVERY_INVENTORY` and `SSH_RECOVERY_KNOWN_HOSTS` select existing
owner-controlled files; they never disable host-key checking. Enabled Ansible
debug is rejected. Only validated connection fields enter the isolated play.

Installed root operations use `/usr/bin/python3 -I -B
/usr/local/lib/vpn-sshd/sshd_bundle.py` with `prepare`, `apply`, `confirm`,
`rollback`, `status`, `recover` or `boot-recover`. Mutation requests use bounded
JSON on stdin; preserve generation/nonce receipts only in private storage.
Preparation requires complete global and direct/Tailnet OpenSSH policy parity
and installed recovery readiness. Unconfirmed activation expires and rolls back;
boot recovery runs before SSH listeners. Unexpected file drift or corrupt state
is an explicit failure that retains evidence for console/rescue recovery.

Do not delete transaction state, install journals or old code generations to
clear a refusal. Retry an interrupted installation only with its same generation.
Full network rollback, strict post-activation connection promotion and real
disconnect/reboot staging acceptance remain separate gates. Until those pass,
this foundation is not permission for production ownership migration or a
substitute for ordinary desired-state configuration.
The current baseline template still reinstates duplicate authentication
directives; align baseline and fresh-bootstrap ownership before migrating real
nodes, so the next ordinary deploy cannot undo the ownership invariant.

## What blocks rollback

- **Lost Terraform state** — without state, Terraform doesn't know about
  blue. You can `terraform import` to recover, but it's manual. See
  `RUNBOOK-incident.md` § "State loss".
- **Lost SOPS secrets** — without secrets, you can't redeploy onto green.
  Restore from out-of-band backup of the SOPS file or treat as full
  rotation event.
- **Single shared subscription URL** — if every client uses the same
  bare-IP URL, switching IPs requires reissuing every URL. Move to
  per-device subscription tokens (see `subscription-host` role) to make
  this a non-event.

## When to skip rollback and rotate instead

- If the failure is "REALITY private key suspected leaked" or "operator
  workstation compromised", rollback is wrong — you need rotation. See
  `RUNBOOK-rotate.md`.
- If the failure is "IP got blocklisted by ASN", rollback to a previous
  config doesn't help. Blue-green to a new VPS in a different ASN.
