---
id: SEC-1787497526094023
title: Validate make variable values against make expansion metacharacters
kind: bug
status: done
area: security
priority: medium
risk: high
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1787497526094023-vpnd-make-variable-hardening
created: 2026-08-23
updated: 2026-09-08
related_tasks: []
closed_at: "2026-09-08T12:02:00Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "PR #203 rebase-merged through protected main as 6bda37bc0476adaef9b6b95eb03778cb890bdf42; local cargo fmt, clippy -D warnings and cargo test (191 tests, 0 failures) on final source commit 6972f6ed; exact-main CI run 34220827411 passed all required checks including vpnd cargo test, clippy, MSRV, dependency policy, SBOM and task-contract; OpenSpec change archived as 2026-09-08-sec-1787497526094023-vpnd-make-variable-hardening with the vpnd/make-interface capability synced to main specs."
---

## Goal

Values vpnd forwards into make command-line assignments cannot execute or unquote inside recipe shells; one choke point validates every KEY=VALUE against a per-key charset allowlist.

## Audit evidence

| Finding | Evidence |
|---|---|
| target_with interpolates values without charset validation | make.rs:36-41 `format!("{}={}", k, v)` |
| Recipes reference values inside shell double quotes | Makefile:630 `--host $(HOST)`; :559,573 `"$(MATRIX_CONFIG)"` |
| Unvalidated sources: CLIENT, HOST, PLAN, ENV, PROVIDER | share.rs:100; probe.rs:18-22 (free-text --host); fleet.rs:14-22; make.rs:26-27 |
| Make expands command-line assignments recursively at recipe use ($$→$, $(shell) executes) | standard GNU make semantics against the quoted recipe references above |

## Acceptance criteria

- Metacharacter-bearing value aborts before spawn naming key and rule.
- Legitimate identifier/path/IP values pass unchanged across all call sites.
- Per-key acceptance/rejection table tests cover CLIENT, HOST, TARGET_ID, MATRIX_CONFIG, PLAN, ENV, PROVIDER.
