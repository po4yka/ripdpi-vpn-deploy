---
id: TST-1787497584762133
title: Close vpnd audit test coverage gaps
kind: chore
status: review
area: testing
priority: high
risk: standard
owner: vpnd implementation
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-23
updated: 2026-08-27
spec_reason: regression-tested-single-module
related_tasks: []
status_detail: Implementation and targeted regressions passed; final source CI and closure lifecycle remain pending.
---

## Goal

Close the test-coverage gaps the vpnd audit surfaced: vacuous tests replaced with real coverage of update cache logic, redaction, registry IO, process runner execution paths, and the probe-matrix analysis branches that currently only pass via implementation-shaped properties.

## Audit evidence

| Gap | Evidence |
|---|---|
| update_cache tests vacuous; real cache/fetch/notice logic never invoked | tests/update_cache.rs:52-155 (assert_eq!(x, x.clone()) at :155; std starts_with tested at :130-147); update.rs has no inline tests |
| doctor_bundle tests re-implement redact locally with triple escape hatches | tests/doctor_bundle.rs:14-24,126-131 (passes trivially on error/missing bundle) |
| Production IO untested: Registry::save/load, Cmd::run/capture | tests/host_crud.rs and tests/registry_roundtrip.rs bypass production functions; process.rs:94-158 has zero execution-path coverage |
| proptest_redact locks in the stale implementation-shaped contract | tests/proptest_redact.rs:38 strategy excludes near-miss inputs |
| Missing behavior tests: malformed/empty YAML, windows() recovery, parse_duration, validate_config/profiles reject branches, transport_fingerprint secret-exclusion, validate_token | secrets.rs:100-103; probe_matrix.rs:563-597,767-782; share.rs:40-50 |

## Acceptance criteria

- update cache expiry/refresh/corrupt-cache paths covered by tests calling the real functions.
- doctor bundle tests call the production redact_secrets; escape hatches removed.
- Registry save/load and Cmd run/capture execution paths covered (nonzero exit, missing binary, signal death).
- Property tests assert requirement-shaped properties (no secrets-path in output for any runtime dir shape).
- Rejection-branch tests for validate_config/validate_profiles and the fingerprint-secrecy property land.

## High-priority implementation ownership

- The vpnd subagent owns vpnd source/tests for behavior coverage, coordinating with its share/probe-matrix fixes.
- The primary agent serializes task/OpenSpec records, generated board, Makefile, shared CI/toolchain files, documentation inventory, staging, commits, and remote delivery. Agents do not commit or mutate credentials/infrastructure.
- Worktree: `codex/complete-high-review`. All writers preserve unrelated changes and coordinate shared-file edits.

## Regression fixes exposed by real tests

Coverage exercises the existing public contracts instead of parallel test-only
implementations. Narrow fixes remain inside their owning vpnd modules: release
tag comparison and future-dated cache expiry, newline-bearing diagnostic path
redaction, refusal of empty non-mapping secrets, and registry directory-path
errors. No new CLI flag, configuration schema, or cross-layer contract is added.
Process-group cancellation and private output publication belong to the linked
probe/share OpenSpec changes, with tests reused here.
