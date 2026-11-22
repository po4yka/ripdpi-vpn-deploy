# Change: Move OpenTofu state to an encrypted Backblaze B2 backend

Task ID: `TFR-1795328481774241`

## Why

All OpenTofu state lives on the MacBook (local backend, one workspace per `PROVIDER`/`ENV`, see `scripts/terraform-env.sh`), so CI cannot plan or apply while the MacBook is off. State holds provider-generated credentials and topology, so it may leave the MacBook only encrypted on the client side. Part of W3 of epic `EPC-1795327697650892`.

## What Changes

- Every root (`terraform/providers/{hetzner,scaleway,upcloud,vultr}`, `terraform/exception/cascade-ingress`, and later `terraform/ops/egress-proxy` from W5 and `terraform/dns/porkbun` from W6) gets an OpenTofu `encryption` block for state and plans (AES-GCM, PBKDF2 key provider, passphrase from the environment), first with an `unencrypted` migration fallback, then `enforced`.
- BREAKING: every root uses a partial `backend "s3"` pointed at a private Backblaze B2 bucket with versioning, Object Lock default retention and lifecycle rules. Backend values (bucket, endpoint, region, keys) come from a `*.s3.tfbackend` file in the ops repository (W1); credentials come only from environment variables.
- Bucket-scoped B2 application keys: read-only for plan, read-write for apply, and a separate operator-only key for the recovery prefix.
- Locking: B2 is reported not to support the conditional `PutObject` that `use_lockfile` needs. This change adds a probe that tests it; until the probe passes, writers are serialized by a per-root CI concurrency group and a break-glass hold procedure, and `use_lockfile` stays off.
- An exact, backed-up, per-root migration of the current local states with address, lineage and serial comparison and a no-change plan before and after.
- `backup-state`/`restore-state` work against B2 object versions; the sealed operator-kit recovery archive moves to the B2 recovery prefix.

## Capabilities

### New Capabilities

- `terraform/encrypted-remote-state`: encrypted remote state and plans, backend layout, access keys, writer serialization, migration and recovery.

### Modified Capabilities

- None in `openspec/specs`.

## Impact

- Terraform layer: `versions.tf` (backend and encryption) of every root; `scripts/terraform-env.sh`, `policy-plan.sh`, `backup-tf-state.sh`, `restore-tf-state.sh`, new `scripts/b2-backend-probe.py`; `Makefile` (`init`, `backup-state`, `restore-state`, `tf-test` keeps `-backend=false`).
- New external resources (authorized live steps): one B2 bucket and three application keys.
- Secrets: one new state passphrase (CI environment secret in W4 plus operator password-manager copy).
- Docs: `docs/reference/secrets.md`, `docs/how-to/deploy.md`, new break-glass section, `terraform/CLAUDE.md`.
