# Change: Move OpenTofu state to an encrypted, locked object storage backend

Task ID: `TFR-1795328481774241`

## Why

All OpenTofu state lives on the MacBook (local backend, one workspace per `PROVIDER`/`ENV`, see `scripts/terraform-env.sh`), so CI cannot plan or apply while the MacBook is off. State holds provider-generated credentials and topology, so it may leave the MacBook only encrypted on the client side. Part of W3 of epic `EPC-1795327697650892`.

## What Changes

- Every root (`terraform/providers/{hetzner,scaleway,upcloud,vultr}`, `terraform/exception/cascade-ingress`, and later `terraform/ops/egress-proxy` from W5 and `terraform/dns/porkbun` from W6) gets an OpenTofu `encryption` block for state and plans (AES-GCM, PBKDF2 key provider, passphrase from the environment), first with an `unencrypted` migration fallback, then `enforced`.
- BREAKING: every root uses a partial `backend "s3"` pointed at a private Scaleway Object Storage bucket (`fr-par`) with versioning and Object Lock default retention. Backblaze B2 was the first choice but rejects the conditional write that the OpenTofu lock needs (HTTP 501). Backend values (bucket, endpoint, region, key layout) come from a `*.s3.tfbackend` file in the ops repository; credentials come only from environment variables.
- Use separate bucket-scoped identities for CI plan, CI apply, operator state access and the operator recovery archive.
- Qualify native locking with concurrent CI and operator writers, including during a GitHub outage. Keep local state authoritative until the backend passes.
- An exact, backed-up, per-root migration of the current local states with address, lineage and serial comparison and a no-change plan before and after.
- `backup-state`/`restore-state` work against bucket object versions; the sealed operator-kit recovery archive and pre-migration backups move to the B2 recovery prefix.

## Capabilities

### New Capabilities

- `terraform/encrypted-remote-state`: encrypted remote state and plans, backend layout, access keys, writer serialization, migration and recovery.

### Modified Capabilities

- None in `openspec/specs`.

## Impact

- Terraform layer: `versions.tf` (backend and encryption) of every root; `scripts/terraform-env.sh`, `policy-plan.sh`, `backup-tf-state.sh`, `restore-tf-state.sh`, new `scripts/state-lock-probe.sh`; `Makefile` (`init`, `backup-state`, `restore-state`, `tf-test` keeps `-backend=false`).
- New external resources (authorized live steps): one Scaleway bucket with a bucket policy and three IAM applications (plan, apply, operator); one B2 bucket with an operator-only recovery key.
- Secrets: one new state passphrase (CI environment secret in W4 plus operator password-manager copy).
- Docs: `docs/reference/secrets.md`, `docs/how-to/deploy.md`, new break-glass section, `terraform/CLAUDE.md`.
