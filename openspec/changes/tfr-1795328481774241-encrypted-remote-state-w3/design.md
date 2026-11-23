## Context

See `proposal.md`. W2 made OpenTofu the CLI. Today each root uses local state; `scripts/terraform-env.sh` maps `ENV=prod` to the `default` workspace and other environments to same-named workspaces with `TF_DATA_DIR` per workspace. `scripts/backup-tf-state.sh`/`restore-tf-state.sh` age-encrypt snapshots to `BACKUP_DEST`. B2 research (2026-11-22): Object Lock works through the S3 API (including enabling it on an existing bucket), application keys can be limited to one bucket and a name prefix with listed capabilities, the S3 API rejects object tagging, and a third-party report says B2 returns HTTP 501 for `PutObject` with `If-None-Match`; no Backblaze page documents conditional writes.

## Goals / Non-Goals

- Goal: CI and the MacBook use one encrypted remote state per root and workspace.
- Goal: a stolen CI key cannot destroy history.
- Non-goal: KMS or a secret server; the passphrase is a static secret in a GitHub environment (W4) and the operator password manager.
- W7 schedules work. The state backend arbitrates writes from both CI and the workstation, including during a GitHub outage.

## Decisions

- Key provider `pbkdf2` with `passphrase = var.state_passphrase` (sensitive, from `TF_VAR_state_passphrase`), method `aes_gcm`, both `state` and `plan`. Rejected: `aws_kms`/`gcp_kms` (new cloud account), `openbao` (a server that holds secrets, against the secretless-egress decision), `external` (custom code).
- Migration fallback: `method "unencrypted" "migrate" {}` and `fallback { method = method.unencrypted.migrate }`, removed with `enforced = true` once every workspace of the root is migrated. Method and provider names stay fixed after encryption, because OpenTofu needs a fallback for any rename.
- Partial backend `backend "s3" {}`; per-root file `config/backend/<root>.s3.tfbackend` in the ops repository with `bucket`, `key = "state/<root>/terraform.tfstate"`, `workspace_key_prefix = "state/workspaces"`, `region`, `endpoints = { s3 = "https://s3.<region>.backblazeb2.com" }`, `use_path_style = true`, `skip_credentials_validation`, `skip_region_validation`, `skip_requesting_account_id`, `skip_metadata_api_check`, and no tags. `skip_s3_checksum` is set only if the probe shows B2 rejects the SDK checksum headers; a third-party report says Object Lock buckets require an MD5 or checksum header, so the default may be the right one.
- Validation paths stay offline: `make validate` and `make tf-test` use `init -backend=false` as today.
- Bucket: one private bucket, Object Lock on at creation, default retention governance 30 days, lifecycle `daysFromHidingToDeleting` greater than the retention. Prefixes: `state/` (state objects) and `recovery/` (sealed operator-kit archive, pre-migration backups).
- Keys (B2 application keys, all bucket-restricted):

| Key | Prefix | Capabilities | Holder |
|---|---|---|---|
| `state-plan` | `state/` | listFiles, readFiles | `tofu-plan` environment (W4) |
| `state-apply` | `state/` | listFiles, readFiles, writeFiles | `tofu-apply` environment (W4) |
| `recovery-operator` | `recovery/` | listFiles, readFiles, writeFiles | operator password manager only |
| `state-operator` | `state/` | listFiles, readFiles, writeFiles | operator password manager only, for state operations and restore |

  No state writer receives permanent version deletion or governance bypass. Production uses `state/<root>/terraform.tfstate`. A named workspace uses `state/workspaces/<workspace>/state/<root>/terraform.tfstate`.
- Require `use_lockfile = true` for every writer. Before migration, exercise the actual OpenTofu lock with the intended identities and bucket retention settings on disposable state: acquire, reject a concurrent writer, release and reacquire from the other client. A successful conditional PUT alone is insufficient. If this fails, keep local state authoritative and defer migration until a compatible backend or independent lock is approved and passes the same tests. Read-only plans use `-lock=false` with the read-only key.
- `backup-state` reads the current state through `state pull` using `state-operator` and seals an age snapshot in the operator kit. `restore-state` reads the selected retained version and writes it with `state push` through the backend lock using `state-operator`. The script holds the same S3 lock as OpenTofu while it reads the current state, checks lineage, pushes the next serial and verifies the stored result. A writer that already holds the lock blocks restore. Version history is preserved and the serial advances. The operator obtains both scoped keys and the passphrase independently of CI.

## Contracts and ownership

- Roots: `versions.tf` of all five roots (W5 and W6 add their roots with this block from the start).
- `scripts/terraform-env.sh` (passes `-backend-config`, keeps the workspace mapping), `scripts/policy-plan.sh` (encrypted saved plan), `scripts/backup-tf-state.sh`, `scripts/restore-tf-state.py` (replaces `restore-tf-state.sh`), new `scripts/state-lock-probe.sh` with `tests/unit/test_state_lock_probe.py`, `Makefile` lane after W2.
- Ops repository: `config/backend/*.s3.tfbackend`; the W1 validator gains the credential check.
- Secrets: `TF_VAR_state_passphrase`, `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` (B2 key ID and key) in the W4 environments.

## Risks / Trade-offs

- A disconnected writer may still hold the backend lock. An operator write must wait or fail closed. Investigate a stale lock and verify the prior writer has stopped before any separately authorized unlock.
- Passphrase loss makes state unreadable → passphrase in two independent places (GitHub environment secret and operator password manager); restore test reads a state with the password-manager copy.
- B2 S3 incompatibility with SDK checksums → the probe tests both settings before migration.

## Migration Plan

After a successful lock and recovery probe, migrate each root and workspace from the MacBook under authorization, with no CI writer configured yet:

1. `make backup-state` (existing local age backup) and record `sha256` of the plaintext file, `tofu state list`, `lineage` and `serial` (values printed are addresses and metadata, not attributes) into a receipt.
2. Commit the encryption block with fallback and the partial backend; run `tofu init -migrate-state -backend-config=<ops>/config/backend/<root>.s3.tfbackend` and accept the copy.
3. Compare address list and lineage; serial must not decrease. Run `tofu plan` and require no changes.
4. Run the probe in inspect mode on the stored object: payload encrypted.
5. After all workspaces of the root pass, remove the fallback, set `enforced = true`, plan again with no changes.
6. Rename the local state file to `*.migrated` (no delete) until the epic drill passes; then move its encrypted backup to `recovery/` and remove the local copy.

Rollback before step 5: `tofu init -migrate-state` back to `backend "local"` with the fallback still present, or restore the step 1 backup. Rollback after step 5: restore from a retained Scaleway version with the passphrase. The inert cascade root has an encrypted local backend and no live resource to migrate. Disposable CI uses an isolated encrypted local backend.

## Open verification questions

1. Does B2 support the full OpenTofu lock lifecycle under the production key scopes and retention settings? Failure blocks migration.
2. Does B2 accept OpenTofu's S3 SDK default checksum headers on an Object Lock bucket, or is `skip_s3_checksum` required? The probe tests both.
3. Does B2 `PutBucketVersioning` behave as AWS does, or are versions always kept? Docs were not read; the probe lists versions after two writes.
4. Does `tofu init -migrate-state` from local to S3 preserve every non-default workspace in one run? Check on a throwaway root first.
5. Is a 30-day governance retention compatible with the B2 lifecycle rule and with cost? Confirm in the bucket settings during the live step.

## Implementation findings (2026-11-22)

- Backblaze B2 rejects the conditional `PutObject` of the OpenTofu lock with HTTP 501 NotImplemented, so no B2 client can take the backend lock. B2 prefix-scoped keys also need `listBuckets` and `readBucketEncryption`, or the S3 `HeadObject` returns 403 on an SSE-B2 bucket. B2 keeps the `recovery/` prefix with the operator-only `tofu-recovery-operator` key; its state keys were deleted.
- Scaleway Object Storage (`fr-par`, bucket `vpn-service-tofu-state-3c5994bc6fde`, versioning, Object Lock governance 30 days) passes the probe with the intended identities: the apply client creates encrypted state, the operator client is refused while the lock is held, the lock releases and the operator re-acquires it, the plan identity reads with `-lock=false` but its lock attempt gets 403, and the apply identity cannot delete the state object or write outside `state/`. The stored object holds only `encrypted_data`, `encryption_version`, `lineage`, `meta` and `serial`. Default SDK checksums work, so `skip_s3_checksum` is not set.
- Identities replace the B2 key table: Scaleway IAM applications `tofu-state-plan` (ObjectStorageObjectsRead, ObjectStorageBucketsRead), `tofu-state-apply` and `tofu-state-operator` (plus ObjectStorageObjectsWrite and ObjectStorageObjectsDelete). IAM policies apply to the whole project; the bucket policy narrows them: plan may get and list `state/`, writers may get, put and list `state/` and delete only `state/*.tflock`, and the operator user keeps full access. Backend files use `endpoints = { s3 = "https://s3.fr-par.scw.cloud" }` and `region = "fr-par"`.
- Scaleway lifecycle rules do not replace the B2 hidden-version rule; versions accumulate (small objects). A retention cleanup is a later decision, not a migration gate.
- Open questions 1 to 3 are answered by the findings above.
- Restore needs `s3:ListBucketVersions` and `s3:GetObjectVersion`; the bucket policy grants them to the `state-operator` application only (statement `OperatorRestore`). `restore-tf-state.py` decrypts a version through OpenTofu in a private local root and pushes it with `state push -`; OpenTofu may raise the serial once more on persist, so the script reports the serial read back. `backup-tf-state.sh` reads through `state pull` into age; the bucket's recovery copy is the age snapshot kept by the operator kit.
- Scripts that read `terraform.tfstate` paths directly (`cloud_promotion_scope.py`, `recovery_promotion.py`, `recovery_runtime.py`, `tailnet-network-promotion.py`, `observability-staging-cleanup.py`, `ci-real-deploy.py`, `audit-permissions.sh`) do not see migrated state. Moving them onto `state pull` is follow-up work outside this change; until then they work only for roots and workspaces that still use local state.
