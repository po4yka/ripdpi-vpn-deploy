---
id: TST-1787497584762133
title: Close vpnd audit test coverage gaps
kind: chore
status: backlog
area: testing
priority: high
risk: standard
owner: po4yka
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-23
updated: 2026-08-23
spec_reason: test-only
related_tasks: []
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
