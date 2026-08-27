---
id: CIC-1787495848795458
title: Add conftest Rego gate to the local union gate
kind: bug
status: review
area: ci
priority: high
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-23
updated: 2026-08-27
spec_reason: tooling-only
related_tasks: []
status_detail: Implementation and targeted regressions passed; exact-source hosted CI and final closure remain pending.
---

## Goal

`terraform/policy/` conftest tests run in the local union gate: `make ci-fast` (and therefore `make check`) executes `conftest verify --rego-version v0 -p terraform/policy/`, eliminating the last green-local-red-CI gap for Rego policy changes.

Execution plan: `plans/006-conftest-gate-local-parity.md`.

## Acceptance criteria

- New `tf-policy-verify` target passes on the clean repo and fails on an intentionally broken policy (positive+negative proof).
- `ci-fast` invokes the target; conftest version pinned in `mise.toml` matching CI.
- `docs/TESTING.md` parity row updated.
