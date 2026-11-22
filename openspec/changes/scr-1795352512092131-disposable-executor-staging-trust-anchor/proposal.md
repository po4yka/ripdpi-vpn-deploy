# Change: Trust an explicit staging TLS anchor in the disposable liveness executor

Task ID: `SCR-1795352512092131`

## Why

A disposable staging node serves the self-signed certificate that its generated staging secrets hold (`scripts/ci-bootstrap-secrets.sh`). The liveness profiles require verified TLS, and the operator Colima executor that `make prepare-disposable-liveness` creates trusts only the distribution roots. The 2026-11-22 staging run therefore stopped at `onboarding-refused`, and three changes kept `staging_evidence: Partial`. Hosted CI already solves the same problem for its disposable runner: `scripts/ci-real-deploy.py` installs only that run's generated certificate into the runner's trust store and keeps verification on. The operator executor has no equivalent input.

## What Changes

- `make provision-disposable-liveness-runtime` accepts an optional `STAGING_TRUST_ANCHOR` path to one PEM certificate.
- The provisioning script validates the certificate locally (exactly one certificate, self-signed, currently valid, exactly one non-wildcard DNS subject alternative name) before it changes the executor, installs it into the executor's system trust store and reports its SHA-256 fingerprint.
- Without `STAGING_TRUST_ANCHOR` the command behaves as before.
- TLS verification in the liveness profiles is unchanged; `insecure` stays refused.

## Capabilities

### New Capabilities

- `operations/disposable-liveness-trust-anchor`: explicit, validated staging trust anchor for the one-shot disposable liveness executor.

### Modified Capabilities

- None.

## Impact

- `scripts/provision-disposable-liveness-runtime.py`, its Make target and Make command-variable boundary, `tests/unit/test_provision_disposable_liveness_runtime.py`, `tests/unit/test_disposable_liveness_make.py`, `docs/reference/protocol-liveness.md`.
- Only the disposable Colima executor changes; it is deleted at de-onboarding. No Terraform, Ansible role, secrets schema, client contract or production node changes.
