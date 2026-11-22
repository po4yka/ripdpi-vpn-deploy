# Change: Migrate the Terraform toolchain to OpenTofu

Task ID: `TFR-1795328347526492`

## Why

State and plan files hold provider-generated credentials and node topology. Terraform encrypts neither on the client side, so a remote backend would hold them in plaintext. OpenTofu has built-in client-side state and plan encryption, which W3 needs to move state off the MacBook. Part of W2 of epic `EPC-1795327697650892`.

## What Changes

- BREAKING: the infrastructure CLI changes from `terraform` 1.15.9 to an exact OpenTofu pin (`tofu`) in `mise.toml`, every CI workflow, the Make targets, scripts and `vpnd`.
- Provider lock files are regenerated from `registry.opentofu.org` with hashes for every CI and operator platform.
- `required_version` in every root becomes an OpenTofu constraint.
- `make tf-test` runs the existing `mock_provider` tests with `tofu test`; `make tf-policy-verify` and the conftest plan policies run unchanged against `tofu show -json` output.
- Docs, folder notes and generated references name OpenTofu. Directory names (`terraform/`) and Make target names stay, so operator commands do not change.

## Capabilities

### New Capabilities

- `terraform/opentofu-toolchain`: the pinned infrastructure CLI, its provider locks, and the checks that must pass under it.

### Modified Capabilities

- None in `openspec/specs/terraform`; existing capabilities describe resources, not the CLI binary.

## Impact

- Terraform layer: all five roots (`terraform/providers/{hetzner,scaleway,upcloud,vultr}`, `terraform/exception/cascade-ingress`).
- CI: `.github/workflows/ci.yml`, `tf-policy.yml`, `daily-security.yml`, `drift.yml`; `mise.toml`.
- Scripts that call `terraform` (`scripts/terraform-env.sh`, `policy-plan.sh`, `render-inventory.sh`, `destroy.sh`, `blue-green.sh`, `backup-tf-state.sh`, `restore-tf-state.sh`, `tf-policy-test.sh`, `drift-since-tag.sh`, `audit-permissions.sh`), `vpnd/src/vpnd/runner/terraform.py` and its callers, `tests/stubs/bin/terraform`.
- Local state stays at its current path in this change; W3 moves it.
