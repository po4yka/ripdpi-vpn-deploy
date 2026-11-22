# Change: Read OpenTofu state through the encrypted backend in every script

Task ID: `TFR-1795357890236562`

## Why

W3 (`TFR-1795328481774241`) moved every production OpenTofu workspace to an encrypted S3 backend with enforced client-side encryption. Scripts that read `terraform/providers/<provider>/terraform.tfstate` or `terraform.tfstate.d/<ENV>/terraform.tfstate`, or that take a state file path from the operator, no longer see the state: the files do not exist, and a local state would be ciphertext. The label-gated disposable CI deploy can no longer initialize, because `init` requires `TF_BACKEND_ROOT` and every root requires `TF_VAR_state_passphrase`. Part of epic `EPC-1795327697650892`.

## What Changes

- New `scripts/tofu_state.py`: one bounded, in-memory `terraform-env.sh state pull` for a provider and environment. An empty workspace reads as no state; any failure refuses.
- The cloud promotion scope, recovery promotion, recovery runtime, observability staging cleanup and CI seed cleanup read state through it. The recovery runtime forwards the state identity, passphrase and backend root to its children.
- BREAKING: the staging cleanup guards (UpCloud and Vultr), unbound staging retirement and tailnet bootstrap drop `--state` and `STAGING_CLEANUP_STATE`; cleanup manifests bind only the state digest, and every read pulls the state of the manifest's provider and environment. Old manifests are refused.
- BREAKING: tailnet network promotion drops the snapshot `state_path`, the `-state=` plan flag and the controller `provider_state_path`; it pulls state through its trusted OpenTofu binary and passes exactly the state identity and passphrase to it.
- The observability cleanup manifest drops `state_path`.
- The disposable CI deploy writes a gitignored `backend "local"` override and a per-run passphrase and backend file in its private work directory. Its state never reaches the bucket and needs no CI bucket identity (W4 unchanged); the age recovery bundle carries the encrypted state and its passphrase.
- `audit-permissions.sh` drops the local state checks.

## Capabilities

### New Capabilities

- `terraform/remote-state-readers`: how scripts read OpenTofu state after the move to the encrypted backend, and the disposable CI backend.

### Modified Capabilities

- None in `openspec/specs`.

## Impact

- Scripts: `tofu_state.py` (new), `cloud_promotion_scope.py`, `recovery_promotion.py`, `recovery_runtime.py`, `observability-staging-cleanup.py`, `ci-real-deploy.py`, `ci-ssh-seed.py`, `audit-permissions.sh`, `staging-cleanup-guard.py`, `vultr-staging-cleanup-guard.py`, `retire-unbound-staging-client.py`, `retire-unbound-staging-executor.py`, `bootstrap-tailnet.py`, `tailnet-network-promotion.py`, `tailnet-network-controller.py`; `Makefile` staging cleanup and retirement targets.
- Docs: `docs/how-to/deploy.md`, `docs/how-to/ci-real-deploy.md`, `docs/how-to/restore.md`, `docs/explanation/architecture-rationale.md`, `terraform/README.md`, folder notes.
- No Terraform, Ansible or client change. No live action; the next authorized staging run proves the runtime paths.
