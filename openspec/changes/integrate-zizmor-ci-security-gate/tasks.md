# CIC-1786295418152915: Integrate zizmor and remediate GitHub Actions security findings

## Objective

Remove the complete repository-owned `zizmor` 1.29.0 default-persona baseline
and make the same strict, exact-version audit a required local and remote CI
capability.

## Ownership

- The primary agent owns `.github/`, `mise.toml`, `Makefile`, affected focused
  tests, `docs/TESTING.md`, and this change's task/evidence files.
- Workflow, Makefile, toolchain, and generated task-board writes are serialized.
- Parallel sub-agents are read-only triage lanes and do not stage or commit.

## Execution

- [x] CIC-1786296210350045 Harden reusable Rust workflow inputs with validated environment values and argument arrays; update its contract tests and run the scoped template-injection audit #feature !high @item:CIC-1786295418152915
- [x] CIC-1786296210412999 Harden pull-request base-ref fetch and diff handling with environment transfer, ref validation, quoted refspecs, and actionlint coverage #feature !high @item:CIC-1786295418152915 @blocked_by:CIC-1786296210350045
- [x] CIC-1786296210451056 Remove dispatch-zone shell expansion from both credentialed deployment workflows through validated `TF_VAR_zone`; run affected workflow and Terraform contract tests #feature !high @item:CIC-1786295418152915 @blocked_by:CIC-1786296210412999
- [x] CIC-1786296210479892 Validate reproducible-build version and digest pins and consume step outputs only through quoted environment variables; run pin and workflow contract tests #feature !high @item:CIC-1786295418152915 @blocked_by:CIC-1786296210451056
- [x] CIC-1786296210502723 Remove the unused branch-protection checkout and disable credential persistence on every remaining flagged checkout; prove no affected job requires authenticated follow-up git operations #feature !high @item:CIC-1786295418152915 @blocked_by:CIC-1786296210479892
- [x] CIC-1786296210530158 Apply a seven-day cooldown to every active Dependabot ecosystem while preserving immediate security updates; add a focused dependency-delivery contract test #feature !high @item:CIC-1786295418152915 @blocked_by:CIC-1786296210502723
- [ ] CIC-1786296210558254 Replace the redundant release-upload action with built-in `gh release upload`, use one resolved tag for tag and manual runs, and prove release asset and rerun behavior with focused tests #feature !high @item:CIC-1786295418152915 @blocked_by:CIC-1786296210530158
- [ ] CIC-1786296210585916 Pin zizmor 1.29.0, add the strict offline Make gate and required least-privilege CI job, add parity/scope tests and operator documentation, then run all named local gates #feature !high @item:CIC-1786295418152915 @blocked_by:CIC-1786296210558254

## Verification

Use the exact gates and evidence categories in `verification.md`. Each checkbox
is committed with its coherent implementation and observed focused checks.
Completion advances the portfolio record at most to `review` until remote CI is
observed on a pushed final SHA.
