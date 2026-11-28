# Change: Manage Porkbun DNS with a pinned OpenTofu root

Task ID: `TFR-1795329107889572`

## Why

The fleet's domains are registered at Porkbun, but the repository has no Porkbun support, so DNS changes need the operator's browser session or the MacBook. CI cannot change a record while the MacBook is off. Part of W6 of epic `EPC-1795327697650892`.

## What Changes

- New OpenTofu root `terraform/ops/porkbun` that manages DNS records of an explicit list of managed domains, with encrypted remote state from the start (W3) and `mock_provider` tests.
- A vetted community Porkbun provider pinned to one exact version with lock-file hashes.
- A conftest policy that refuses records outside the managed domains and TTLs below Porkbun's minimum.
- Per-domain API access: API access is turned on only for managed domains, and the CI keys are limited to those domains, to DNS (apply) or read (plan) permission, and to the egress address (W5).
- Adopt existing records with a reviewed import-only plan and verify an empty follow-up plan.

## Capabilities

### New Capabilities

- `terraform/porkbun-dns`: DNS records of managed Porkbun domains as code, with scoped API access.

### Modified Capabilities

- None.

## Impact

- Terraform: new root, `terraform/policy/` rule and test, `Makefile` `tf-test` and `validate` loops (after W5 in the shared lane).
- Ops repository: `config/tfvars/porkbun/*.tfvars` (domains and records), backend file.
- Secrets: Porkbun API key and secret in `tofu-plan` (read) and `tofu-apply` (DNS) environments (W4 matrix).
- External (authorized live steps): Porkbun per-domain API access and key creation.
