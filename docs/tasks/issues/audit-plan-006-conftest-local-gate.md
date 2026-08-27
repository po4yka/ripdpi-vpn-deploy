---
id: CIC-1787495848795458
title: Add conftest Rego gate to the local union gate
kind: bug
status: done
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
closed_at: "2026-08-27T14:12:47Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Pinned Conftest runs in local and CI gates; policy tests include real negative plans and fail closed without the pinned binary. Implementation verified at 1221ccb59ae90f4d5d7fc3951018dcbef1634841: local make check passed (1055 pytest, one pre-existing network-scan skip, 55 Bats, 79 Terraform tests, 45 Conftest tests, 102 snapshots); hosted CI run 33079404315 passed all 51 jobs. Probe schema synchronization is a separate withheld task."
---

## Goal

`terraform/policy/` conftest tests run in the local union gate: `make ci-fast` (and therefore `make check`) executes `conftest verify --rego-version v0 -p terraform/policy/`, eliminating the last green-local-red-CI gap for Rego policy changes.

Execution plan: `plans/006-conftest-gate-local-parity.md`.

## Acceptance criteria

- New `tf-policy-verify` target passes on the clean repo and fails on an intentionally broken policy (positive+negative proof).
- `ci-fast` invokes the target; conftest version pinned in `mise.toml` matching CI.
- `docs/TESTING.md` parity row updated.
