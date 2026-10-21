# Local operator kit

## Contract

Use `secrets/local/` as the private operator kit on the deployment MacBook.
The existing `.gitignore` rule for `secrets/*` covers the complete tree.
This is an operator storage convention, not a new secrets schema or an automatic
migration. Existing external paths remain supported; command defaults do not change.

The kit must account for all material needed to manage, rebuild, revoke access to,
and recover the service. Keep one authoritative copy of each item. Record working
files that must stay at tool-specific paths instead of making competing copies.
Git ignore prevents ordinary staging; it does not encrypt files, control agent
reads, or provide a backup. Git still tracks a file that was already committed.

## Layout

Paths below are relative to the selected deployment checkout. Names in angle
brackets are technical resource or device IDs, not personal or network labels.

```text
secrets/local/
  README.md                            # private index and recovery order
  catalog.yaml                         # private metadata; no secret values
  config/
    age.key                            # existing software identity, if used
    .sops.yaml                         # real recipient policy
    <scope>.secrets.sops.yaml           # existing deployment schema per scope
    operator-access.sops.yaml           # operator tokens and recovery material
    fleet.mk                           # private configuration included by .fleet.mk
    ssh.conf                           # SSH configuration; no embedded secrets
    known_hosts                        # host identities; verified before use
  keys/                                # SSH identities/certificates, if exportable
  clients/<device-id>/                  # current delivery artifacts; short retention
  state-backups/                       # encrypted Terraform snapshots
  receipts/                            # private grants, revocations, restore results
  recovery/                            # recovery instructions and encrypted exports
  runtime/                             # temporary plaintext; exclude from backups
```

Only create files that are needed. `operator-access.sops.yaml` is a private
operator document, separate from `secrets/schema.json`; do not pass it to Ansible
or the deployment-secret validator. Keep provider/API credentials encrypted at
rest. Expose them only through environment variables for the selected command,
using an approved local credential loader. Keep values out of Make assignments,
Terraform inputs, command arguments, shell history and committed examples.

## Coverage and authority

| Material | Authority and local record |
|---|---|
| VPN server secrets, TLS keys, per-device credentials and subscription grants | Scoped deployment SOPS files; preserve the existing schema and `client_registry`. |
| Cloud, DNS, repository/CI, Tailnet and monitoring access | Operator SOPS file or an existing local credential store; catalog the account, resource scope and credential reference. Include webhook secrets and backup-storage access when used. |
| age and SSH identities | Existing identity or hardware token. Record public fingerprints, expiry, use and recovery references. Copy exportable keys only through an authorized migration. |
| MFA and account recovery | Encrypted recovery material where export is supported; record hardware-token enrollment and the independent recovery route. Keep PINs and backup unlock factors separate from their protected material. |
| Local fleet, SSH, inventory, tfvars, profile and `vpnd` configuration | One active file per purpose; catalog its real path, source template and rebuild method. Tracked profiles remain authoritative for public configuration. |
| Terraform state and saved plans | Keep active state at its existing tool path; retain encrypted state backups with provider, environment and time. Plans are temporary sensitive files, not reusable recovery state. |
| Client delivery files, URLs and QR codes | Derived sensitive output. Recover from the encrypted per-device authority where supported; record exceptions and expire delivery copies. |
| Access grants and operational evidence | Private receipts with issue/revoke/expiry dates and the relevant resource. Token-bearing URLs and raw diagnostics require encryption or redaction. |

An issued access right is a remote grant, not just a local key file. The catalog
records both. Export of other operators' private keys is outside this contract.
For non-exportable keys, one-time tokens, or credentials held only by CI, record
the limitation and an authorized recovery or reissue procedure. Do not invent a
local copy or silently replace credentials that cannot be retrieved.

Each catalog entry has a stable technical ID and these fields:

- Purpose, environment, provider/service, resource and account reference.
- Granted permissions, issuer/grant receipt, and status: active, expired,
  revoked, missing or unverified.
- Authoritative path or local credential-store reference, storage type, and
  public fingerprint when available. Use paths relative to the kit when possible.
- Issue, expiry and rotation dates; last verification date and evidence reference.
- Exact consumer and activation method, revoke/rotate procedure, backup reference
  and restore procedure. Mark unknown or not-applicable fields explicitly.

The private catalog may identify accounts and topology, so protect it like the
kit. It contains references, never passwords, tokens, private keys, recovery
codes, complete subscription URLs or secret-bearing command lines.

## Connect existing tools

Use the ignored root `.fleet.mk` as the Make entry point. It may include the
private `config/fleet.mk`. Treat both as executable configuration and review
them locally before use. For the existing single-environment layout:

```make
SOPS_FILE = $(CURDIR)/secrets/local/config/$(ENV).secrets.sops.yaml
SECRETS_FILE = $(CURDIR)/secrets/local/runtime/vpn-$(ENV).secrets.yaml
```

For multiple host-specific sources, preserve explicit `SOPS_FILES` mappings and
the deployment workflow's per-host selection. Do not collapse scopes into one
shared file. Set `SOPS_AGE_KEY_FILE` in the protected command environment; audit
logging separately uses `AGE_KEY` and `AUDIT_LOG_FILE`. State backup uses
`BACKUP_DEST` and `AGE_RECIPIENT` or `AGE_RECIPIENT_FILE`; see
[secrets operations](../reference/secrets.md) and `scripts/backup-tf-state.sh`.

Make overrides do not configure every caller. Direct scripts can use their own
defaults, and `vpnd` resolves a separate platform configuration directory.
Record and verify each caller's supported inputs before changing its paths.
Keep unavoidable working files outside the kit in the catalog and encrypted
backup coverage. Do not claim all tools use the kit after setting `.fleet.mk`.

Use one physical kit on the MacBook. Additional worktrees refer to its existing
absolute paths in their ignored local configuration; do not duplicate identities
or merge independent environment state. Each worktree needs an explicit target
selection before a live operation. If the owning checkout moves, update and
verify those references before use.

## Protection and recovery

Use owner-controlled directories with mode `0700` and files with mode `0600`.
Create new material with `umask 077`; inspect ownership, ACLs and symlinks before
changing an existing tree. Avoid recursive permission changes on unknown paths.
Use FileVault and encrypted backups for the MacBook. File permissions do not
isolate secrets from tools running as the same user.

Keep durable secrets in SOPS/age, except identities that a tool must read directly.
Use temporary plaintext only for the operation that needs it. `make clean`
removes the selected `SECRETS_FILE`, not every runtime or client artifact.
Account for other temporary output explicitly. Exclude `runtime/`, temporary
plans and plaintext delivery artifacts from backups and file synchronization.
Deletion alone is not proof that snapshots or prior copies no longer contain data.

Keep an encrypted backup independent of this MacBook, and keep its recovery
factor independent of the backed-up kit. A software age key beside SOPS files
does not protect against compromise of the unlocked workstation. Use the
existing [age recovery procedure](age-recovery.md) or an independent recipient
where appropriate; do not put enough recovery shares together in this kit.
Back up durable changes after issuance, rotation and revocation. Preserve the
old recovery material until an authorized restore test succeeds.

Record restore order in the private README: recover the decryption identity,
restore encrypted sources and access, restore configuration and state, then
verify the selected account/resource before live use. Test recovery in a private
temporary location without overwriting active files or applying Terraform.
Record the backup time, restored scope, result and remaining gaps; a local
restore does not prove remote access or deployment health.

## Agent procedure and completion

1. Read this contract before collecting or moving operator material, issuing or
   revoking access, changing local configuration, or preparing recovery.
2. Inspect path metadata and Git coverage first. Use `git check-ignore` for
   proposed paths and `git ls-files -- secrets/local` to detect tracked material.
   Check permissions and ownership without reading secret contents into output.
3. Reconcile the private catalog with the selected deployment configuration and
   known grant receipts. Treat missing files, expired rights, stale backups and
   unverified access as explicit gaps. Do not scan unrelated personal stores.
4. Before a migration, list source/destination paths, authority, consumers,
   backup and rollback steps. Preserve originals until the new consumer and
   recovery path are verified. Credential use, reissue and live verification
   follow the existing authorization boundaries; a documentation request does
   not authorize them.
5. After an authorized change, update the catalog and affected receipts. Use
   categorical checks that do not emit secrets. Report only coverage counts,
   redacted failures and missing acceptance checks in chat or tracked documents.

Call the kit complete only when every in-scope resource and issued access has
an entry, each required item is available or has a verified recovery route,
consumer paths and protections are checked, and an independent backup restore
has passed. Report local completeness and current remote access separately.
Documentation, file presence and green repository checks alone do not meet this bar.
