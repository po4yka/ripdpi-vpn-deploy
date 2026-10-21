# Runbook — credential rotation

> **Status:** Current · **Type:** how-to · **Tier:** CORE · **Reviewed:** 2026-10-21

## Purpose and scope

Rotate credentials at the smallest scope that addresses the threat: one
device, the server-wide REALITY keypair, the Hysteria or AmneziaWG server
keys, the restic password, or the deploy user's SSH key.

Three rotation scopes. Pick the smallest one that addresses the threat.

Infrastructure rotation caused by sustained protocol failure is separate from credential rotation. Follow `docs/reference/protocol-liveness.md`: only fresh authenticated client-path failures with a successful direct control can create a quorum candidate, and the resulting OTP still enters the normal blue-green verification and operator-confirmation flow.

## Preconditions

- The threat is identified and the scope chosen; a sustained protocol failure is an infrastructure rotation under [protocol liveness](../reference/protocol-liveness.md), not a credential rotation.
- The encrypted secrets file is the only durable copy; keep its previous generation until the rotation is verified.
- Each guarded block below decrypts, acts on one exact node and shreds plaintext on every exit path; run one block per node.

## Authorization

Every target below that uses cloud credentials, inventory, SSH or decrypted secrets needs the operator's authorization for this environment, target and plan before it runs ([decision boundaries](../../AGENTS.md#decision-boundaries)). A reviewable plan or dry-run precedes every mutation. `rotate-credentials` is an exact-node verb: one alias per invocation, one authorization per node.

## 1. Single client leak

A device was lost / stolen / decommissioned, or one client URI showed up
where it shouldn't.

```bash
# Edit the encrypted secrets file
sops ~/.config/vpn-provision/prod.secrets.sops.yaml
```

Remove the leaked client from:

- `xray.clients[*]` (matching `name`)
- `hysteria.clients[*]` (matching `name`)
- `amneziawg_secrets.instances[*].peers[*]` (matching `name`)
- `naive_secrets.clients[*]`, when configured (matching `name`; `make naive-revoke` removes only this transport)
- `snell_secrets.variants[*].users[*]`, when configured (matching `name`)

Keep the encrypted device registry lifecycle and subscription token revocation in
sync with complete device retirement. Naive uses independent per-device passwords;
removing its last client keeps the decoy site and disables proxy forwarding.

Save and exit (sops re-encrypts automatically). `rotate-credentials`
re-renders configs and reloads services on exactly one inventory alias per run.
`ANSIBLE_LIMIT` must be that plain alias (letters, digits, `_`, `.` and `-`,
starting with a letter or digit, at most 128 characters); Make refuses anything
else before it starts `ansible-playbook`. The play refuses a missing limit, a
group, a pattern, a list, and a host whose inventory `env` is not the selected
`ENV`, so run it with the `ENV` and secrets file of that node. The verb starts
`ansible-playbook` without an inherited `ANSIBLE_SKIP_TAGS` or `ANSIBLE_RUN_TAGS`,
which could skip that guard. It also requires a clean checkout and the deploy
pre-checks (`SKIP_PRECHECK=1` skips only the secrets validation and certificate
checks).
The refusal is the first task, after fact gathering and the controller-side load
of the decrypted secrets file, so a refused run may have gathered facts from the
first selected host but changes nothing on any node.

Revocation is incomplete until every node of the environment has been rotated
and verified: a node you skip keeps accepting the removed credential. The aliases
are the host names in the `[vpn]` section of `ansible/inventory/generated.ini`.
Decrypt once, run the pair once per alias with the same `ENV` and stop at the
first failure, then shred the decrypted file. A failed decrypt must not reach the
loop: a plaintext file left by an earlier session would be deployed instead of
your edit, so the loop runs only after a successful decrypt. The sequence runs in
a subshell, so nothing stays set in your shell, and it names the environment once
(`e=prod`); every command reads `$e`, so adapting the block for another
environment changes that one line. It installs the `make clean` cleanup before it
decrypts and turns an interrupt (Ctrl-C), a quit (`Ctrl-\`), a termination or a
hangup into an exit, so the decrypted file is shredded on every exit path the
shell can catch. The cleanup ignores those four signals while it runs, so a
second interrupt cannot cut the shred short. The subshell exits with the status of
the failing step, and the cleanup does not mask it; when only `make clean` fails
after a successful run, the subshell exits 1 and stderr shows "failed to remove
decrypted secrets". A signal sent only to the subshell takes effect once the
running `make` finishes. Cleanup cannot run if the shell is killed outright
(SIGKILL) or the machine loses power; after that, or whenever `make clean` reports
a failure, run `make clean` yourself with the same `ENV`:

```bash
(
  e=prod
  trap 'rc=$?; trap "" INT QUIT TERM HUP; make clean ENV="$e" || [ "$rc" -ne 0 ] || rc=1; exit "$rc"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP
  trap 'exit 131' QUIT
  make decrypt ENV="$e" || { rc=$?; echo "decrypt failed; nothing rotated" >&2; exit "$rc"; }
  for node in <alias-1> <alias-2>; do
    make rotate-credentials ENV="$e" ANSIBLE_LIMIT="$node" &&
      make verify ENV="$e" ANSIBLE_LIMIT="$node" ||
      { rc=$?; echo "stopped at $node" >&2; exit "$rc"; }
  done
)
```

AWG rotation validates the rendered inventory's provider listener contract and
republishes the canonical firewall with current typed peer claims before
reconciling the complete AWG role lifecycle, including obsolete instance retirement.
A failed activation restores the prior firewall and configs together. The normal rendered inventory is required for rotation;
missing or mismatched listener authority refuses before mutation.

Credential rotation enters the authoritative Naive role when enabled, including
native validation and acknowledgement of the activated configuration. Editing the
encrypted source alone does not revoke a running server's access.

For changed Xray configuration, rotation saves the outgoing bytes in
`/etc/xray/config.json.prev` before publication. An unchanged configuration
keeps the existing restore point. This follows the Xray role's change-detection
contract; it is not an automatic rollback if a later service restart fails.

Other clients retain valid credentials; a service restart may interrupt existing
connections. The removed credentials fail authentication after runtime adoption.

## 2. Server-wide REALITY keypair

Use when the REALITY private key is suspected leaked, or you want to
invalidate every existing client URI in one move.

```bash
# Generate new REALITY keypair
docker run --rm ghcr.io/xtls/xray-core x25519
# or: xray x25519

# Update secrets
sops ~/.config/vpn-provision/prod.secrets.sops.yaml
# Replace xray.reality_private_key and xray.reality_public_key

# Optionally regenerate every client's shortId (good hygiene with this rotation)
sops ~/.config/vpn-provision/prod.secrets.sops.yaml
# For each xray.clients[*], replace short_id with `openssl rand -hex 4`

(
  trap 'rc=$?; trap "" INT QUIT TERM HUP; make clean || [ "$rc" -ne 0 ] || rc=1; exit "$rc"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP
  trap 'exit 131' QUIT
  # full deploy — REALITY change is server-wide
  make decrypt &&
    make deploy &&
    make verify
)
```

The deploy sequence runs in the guarded subshell described in [section 1](#1-single-client-leak): the decrypted file is shredded on every exit the shell can catch, and deploy and verify run only after a successful decrypt.

Every existing client URI is now invalid. Reissue URIs to every device
through `OUTPUT=<new private recipient file> scripts/new-client.sh --emit-uri <name>`
and redistribute through the approved private channel. Stdout carries metadata
only; the output requires a new file in a private `0700` directory.

## 3. Hysteria server-wide / AmneziaWG server-wide

If the Hysteria server password format or AWG server private key leaks,
rotate similarly: generate new server-side material, update secrets, run
`make deploy`. AWG client public keys remain valid (only the server
private key changed); Hysteria per-user passwords remain valid (only
server cert / Salamander password changed if applicable).

## 4. Restic password

A planned password change and compromise recovery use different procedures.
Restic stores a repository master key wrapped by one or more password keys.
`restic key passwd` changes the password wrapping and retains the snapshot
history. It does not replace a master key that an attacker already obtained.

### Planned password change

1. Keep the current password and a verified recovery path. Stop the backup and
   restore timers and wait for both services to become inactive.
2. In the authorized private operator session, use `restic key passwd` against
   the current repository. Supply passwords through its private password-file
   interface or protected prompt, never command arguments or logs. Update the
   remote repository key material before testing the new remote password.
3. Store the new password in SOPS and converge the password file through the
   reviewed deployment workflow. A change to `backup.restic_password` alone
   does not update the keys of an existing repository.
4. Run a backup and an isolated restore with the new password. When offsite
   replication is enabled, the restore must use the remote repository. Restore
   the intended timer states only after these checks pass. Retire the old
   password after successful verification.

### Repository master-key compromise

If an attacker had the old password and repository key material, assume the
repository master key is exposed. A wrapping-password change cannot revoke
that knowledge or protect copies of earlier ciphertext.

1. Keep the prior repository and its recovery password. Stop both timers and
   wait for inactive services before changing configuration.
2. Select a distinct local `restic_repo_dir` and, when replication is enabled,
   a distinct `backup.remote.rclone_path` generation in the reviewed profile.
   Generate a new `backup.restic_password`. Never point the replacement
   `rclone sync` at the prior remote generation.
3. Review and deploy those inputs. The role initializes the new repository;
   it does not need to delete or overwrite the previous repository. Use the
   guarded decrypt, deploy and verify sequence from section 1:

```bash
(
  trap 'rc=$?; trap "" INT QUIT TERM HUP; make clean || [ "$rc" -ne 0 ] || rc=1; exit "$rc"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP
  trap 'exit 131' QUIT
  make decrypt &&
    make deploy &&
    make verify
)

```

4. Explicitly run `vpn-backup.service`, then
   `vpn-backup-restore-drill.service`. Both commands must succeed. Check the
   new success marker and confirm that it used the selected generation and,
   when enabled, the remote source. Timer installation alone is not a backup.
5. If any deployment, backup or restore check fails, keep the previous local
   and remote generations and their passwords. Repair or restore the reviewed
   configuration without deleting recovery material.
6. Resume the intended timers after successful verification. Retire the prior
   repository generation and its password only through a separate authorized
   cleanup. Earlier snapshots may still contain exposed application secrets;
   rotate those credentials through their own workflows.

## 5. SSH key for the deploy user

If the operator workstation is compromised:

```bash
# Generate a new key
ssh-keygen -t ed25519 -f ~/.ssh/vpn_deploy_new -N '' -C 'vpn-deploy operator'

# Edit tfvars to put the new public key in admin_ssh_public_key
$EDITOR terraform/providers/upcloud/environments/prod.tfvars

# cloud-init.user_data is ignored by lifecycle, so the new key won't apply
# automatically. Instead, push it via Ansible by adding a temporary one-off
# task — or, faster, SSH in once with the OLD key and run:
ssh-copy-id -i ~/.ssh/vpn_deploy_new.pub deploy@<vps>

# Then revoke the old key on the server
ssh -i ~/.ssh/vpn_deploy_new deploy@<vps>
$EDITOR ~/.ssh/authorized_keys   # remove the old key line
exit

# From now on, use the new key
export ANSIBLE_SSH_PRIVATE_KEY_FILE=~/.ssh/vpn_deploy_new
shred -u ~/.ssh/vpn_deploy
```

If you've truly lost the old key (no remaining SSH access), see
`incident.md` § "lost SSH access".

## What to NOT do during rotation

- Don't reuse a UUID, shortId, peer keypair, or password. Always generate
  fresh.
- Don't keep the previous secrets file around as a "backup". The encrypted
  blob in your SOPS file IS the only durable copy; rotation overwrites it.
- Don't leave the old client entry in secrets and just disable on the
  server. The server is the only enforcement point — secrets are a record
  of what should be enforced. Mismatch breaks rotation hygiene.

## Verification

`make verify ANSIBLE_LIMIT=<alias>` on every rotated node; the rotated device
reconnects with its new material and the revoked identity is refused. The
audit log (`make audit-log`) shows the issuance record.

## Rollback

Keep the previous encrypted generation until verification passes. If a
rotation breaks a device, re-issue that device's material; never restore a
revoked identity. A failed server-wide rotation is recovered by deploying the
previous encrypted generation to the same exact node.

## Evidence to record

The scope rotated, the aliases and devices affected (names only), the verify
results per node and the audit-log entry, in the task or incident record.
