## Context

See `proposal.md`. Terraform 1.15.9 is pinned in `mise.toml` and `hashicorp/setup-terraform` in `ci.yml` and `tf-policy.yml`. Roots declare `required_version = ">= 1.15, < 2.0"`, which OpenTofu would reject because OpenTofu checks the constraint against its own version. Five roots commit lock files. 56 unit test files mention `terraform`, and `tests/stubs/bin/terraform` stands in for the binary. `vpnd` has `runner/terraform.py`.

## Goals / Non-Goals

- Goal: identical behavior and checks under OpenTofu, provable offline.
- Non-goal: encryption or a remote backend (W3); renaming the `terraform/` directory or Make targets.

## Decisions

- Pin the latest stable OpenTofu release at implementation time (1.13.9 was current on 2026-11-05) as an exact version. Rejected: a range, by the repository pin rule.
- Install in CI with `opentofu/setup-opentofu` v2.0.2 pinned by commit SHA, `tofu_wrapper: false` so stdout stays clean for `show -json`, and `checksums` set to the `linux_amd64` zip SHA-256 from the release's `SHA256SUMS`. Rejected: downloading a release tarball by hand, which duplicates checksum logic.
- Recipes and scripts call `tofu` directly. Rejected: a `TF` indirection variable (no second binary to select), and a `terraform` shim symlink (hides the change and keeps the old name alive).
- `required_version = "1.13.9"` in every root, the same exact release as the pin.
- Rename `tests/stubs/bin/terraform` to `tofu`. Keep names that denote the layer rather than the binary: the `terraform/` tree, `scripts/terraform-env.sh`, Make targets such as `terraform-init`, CI job IDs, `vpnd` `runner/terraform.py` (it only calls the wrapper), error codes such as `terraform-still-running`, and the `managed_by = "terraform"` resource labels, whose change would modify live resources.
- Regenerate locks with `tofu providers lock -platform=linux_amd64 -platform=darwin_arm64` per root against an exact-version copy of `versions.tf`, then restore the original constraint string, so provider versions stay unchanged. The four cloud providers keep identical `zh:` archive hashes; `hashicorp/external` in the cascade root resolves to OpenTofu's own build and gets new hashes.
- Dependabot uses its `opentofu` ecosystem for the provider roots; the pre-commit `terraform_fmt` and `terraform_validate` hooks use `--hook-config=--tf-path=tofu`.
- Known divergence check: run `tofu validate` and `tofu test` on every root before changing anything else; if a Terraform-only feature is in use, record it and adjust in the same commit. Found:
  - `run.state_key` (Terraform only): the two fresh-state runs in the Vultr and Scaleway lifecycle tests move into `tests/fresh-key.tftest.hcl`, because every test file starts from empty state.
  - OpenTofu keys test state by the run's module source, so a run cannot switch configurations and keep state. The native harness `tests/unit/test_provider_bootstrap_lifecycle.py` used `state_key` to apply the pre-guard fixture configuration and then plan the current root; a targeted apply cannot replace it, because targeting the server also creates the guards it references. The operator chose to retire the migration, first-adoption and bootstrap-drift cases and their fixtures, because every live state has been applied since the 2026-10-09 guards. The unchanged-identity, identity-edit and newline-key cases remain.
  - OpenTofu mock providers return known random strings for computed IDs in plan mode; Hetzner test files set numeric mock IDs, as `lifecycle.tftest.hcl` already did.
  - `var.<name>` in a test assertion is the raw test value in OpenTofu, not the module's typed value; the Vultr adapter test compares against an explicit typed literal.
  - OpenTofu test teardown cannot destroy `prevent_destroy` resources: it reports the error, keeps the exit status, and writes an ignored `errored_test.tfstate` with mock data. Terraform skips this check during teardown.

## Contracts and ownership

- Roots: `terraform/providers/*/versions.tf`, `terraform/exception/cascade-ingress/versions.tf`, all five lock files.
- `mise.toml`, `Makefile` (`validate`, `plan`, `apply`, `init`, `tf-test`, `terraform-init`), `.github/workflows/{ci,tf-policy,daily-security,drift}.yml`.
- `scripts/*` listed in `proposal.md`, `vpnd/src/vpnd/**`, `tests/stubs/bin/`, affected `tests/unit/*`.
- Docs: `terraform/CLAUDE.md`, `docs/reference/testing.md`, `docs/how-to/deploy.md`, `README.md`, generated `docs/reference/make-targets.md` via `make docs-reference`.

## Risks / Trade-offs

- Provider binaries from the OpenTofu registry differ in signing keys → lock hashes regenerated and reviewed; provider versions unchanged.
- Hidden Terraform-only behavior → full `make check` plus a no-change production plan per root (`REQ-TOFU-STATE-COMPAT`).
- OpenTofu upgrades the state format on first write → this change runs only read-only plans against production; W3 performs the first write under backup.

## Migration Plan

1. Land the toolchain change with all offline gates green (`make check -j 4`).
2. Authorized live step: on the MacBook, `make PROVIDER=<p> ENV=prod plan` for each root with operator credentials; record "no changes" receipts in the ops repository.
3. Rollback: revert the commit; local state was only read.

## Open verification questions

1. Does any root or `mock_provider` test use a Terraform 1.15 feature that OpenTofu 1.13 lacks? Answered by step 3 of execution (`tofu test` per root).
2. Does `tofu show -json` produce any field the conftest policies read in a different shape? Answered by `make tf-conftest` on a fixture plan.
3. Are all four provider versions currently locked available on `registry.opentofu.org` with matching versions? Answered by `tofu providers lock`.
