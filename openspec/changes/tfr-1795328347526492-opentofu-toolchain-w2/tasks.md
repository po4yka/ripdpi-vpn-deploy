# TFR-1795328347526492: Migrate the Terraform toolchain to OpenTofu

## Objective

Every root, script, Make target, CI job and vpnd command uses one exact OpenTofu pin, all offline infrastructure checks pass under it, and each production root plans with no changes against its current local state.

## Ownership

`mise.toml`, `Makefile`, `.github/workflows/{ci,tf-policy,daily-security,drift}.yml`, `terraform/**/versions.tf` and lock files, `scripts/*` that call the CLI, `vpnd/src/vpnd/**`, `tests/stubs/bin/`, affected `tests/unit/*`, `terraform/CLAUDE.md`, docs. First in the shared `Makefile`/`mise.toml` lane (W2 before W3 to W7).

## Execution

- [ ] TFR-1795328401186589 Pin OpenTofu in mise.toml and the CI workflows with a checksum-verified install #feature !high @item:TFR-1795328347526492
- [ ] TFR-1795328413365163 Switch Make targets, scripts, vpnd and stubs from terraform to tofu and regenerate provider lock files #feature !high @item:TFR-1795328347526492
- [ ] TFR-1795328425689060 Run the mock_provider tests and conftest policies under tofu in make tf-test and tf-policy-verify #feature !high @item:TFR-1795328347526492
- [ ] TFR-1795328437282569 Update docs, folder notes and generated references for OpenTofu #feature !high @item:TFR-1795328347526492
- [ ] TFR-1795328448740009 Confirm a no-change tofu plan for every production root against current local state (authorized live step) #feature !high @item:TFR-1795328347526492

## Verification

Local: `make check -j 4` (includes `tf-test`, `tf-policy-verify`, `validate`), `make vpnd-test vpnd-lint vpnd-parity-check`, `make tf-conftest` on a fixture plan. Remote CI: the PR's full check set. Live (authorized): no-change `make plan` receipts for each production root. No deploy, client or artifact change.
