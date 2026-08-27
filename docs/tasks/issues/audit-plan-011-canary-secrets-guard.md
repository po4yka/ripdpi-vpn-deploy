---
id: OPS-1787495859957242
title: Refuse canary deploys scoped to non-canary secrets files
kind: bug
status: done
area: operations
priority: high
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-23
updated: 2026-08-27
spec_reason: regression-tested-single-module
related_tasks: []
status_detail: Implementation and targeted regressions passed; exact-source hosted CI and final closure remain pending.
closed_at: "2026-08-27T14:12:47Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Canary gate tests accept only the documented canary secrets basenames and prove rejected paths do not invoke deployment. Implementation verified at 1221ccb59ae90f4d5d7fc3951018dcbef1634841: local make check passed (1055 pytest, one pre-existing network-scan skip, 55 Bats, 79 Terraform tests, 45 Conftest tests, 102 snapshots); hosted CI run 33079404315 passed all 51 jobs. Probe schema synchronization is a separate withheld task."
---

## Goal

`make deploy-canary` refuses to run when the resolved `SECRETS_FILE`/`SOPS_FILE` are not canary-scoped, so a `.fleet.mk` pin can no longer silently validate prod secrets against canary hosts.

Execution plan: `plans/011-canary-secrets-scoping-guard.md`.

## Acceptance criteria

- Prod-scoped override: exit 2 refusal with actionable message, zero deploy side effects.
- Canary-scoped values pass the guard (recursion line reached under `make -n`).
- Only the `deploy-canary` recipe changed; `make -n check` parses clean.
