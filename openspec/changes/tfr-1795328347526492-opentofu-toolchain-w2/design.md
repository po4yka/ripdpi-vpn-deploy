## Context

See `proposal.md`. Terraform 1.15.9 is pinned in `mise.toml` and `hashicorp/setup-terraform` in `ci.yml` and `tf-policy.yml`. Roots declare `required_version = ">= 1.15, < 2.0"`, which OpenTofu would reject because OpenTofu checks the constraint against its own version. Five roots commit lock files. 56 unit test files mention `terraform`, and `tests/stubs/bin/terraform` stands in for the binary. `vpnd` has `runner/terraform.py`.

## Goals / Non-Goals

- Goal: identical behavior and checks under OpenTofu, provable offline.
- Non-goal: encryption or a remote backend (W3); renaming the `terraform/` directory or Make targets.

## Decisions

- Pin the latest stable OpenTofu release at implementation time (1.13.9 was current on 2026-11-05) as an exact version. Rejected: a range, by the repository pin rule.
- Install in CI with `opentofu/setup-opentofu` pinned by commit SHA and `tofu_wrapper: false`, so stdout stays clean for `show -json`. Rejected: downloading a release tarball by hand, which duplicates checksum logic.
- One Make variable `TF ?= tofu` used by every recipe, and scripts use `${TF:-tofu}`. Rejected: a `terraform` shim symlink, which hides the change and keeps the old name alive.
- `required_version = "~> 1.13.9"`-style exact-minor constraint in every root, matching the pin.
- Rename `tests/stubs/bin/terraform` to `tofu` and `vpnd` `runner/terraform.py` to `runner/tofu.py`, updating every caller and the `vpnd` parity map (`make vpnd-parity-check`).
- Regenerate locks with `tofu providers lock -platform=linux_amd64 -platform=darwin_arm64` per root, provider versions unchanged.
- Known divergence check: run `tofu validate` and `tofu test` on every root before changing anything else; if a Terraform-only feature is in use, record it and adjust in the same commit.

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
