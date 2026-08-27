---
id: OPS-1787495859957242
title: Refuse canary deploys scoped to non-canary secrets files
kind: bug
status: review
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
status_detail: Implementation and targeted regressions passed; final source CI and closure lifecycle remain pending.
---

## Goal

`make deploy-canary` refuses to run when the resolved `SECRETS_FILE`/`SOPS_FILE` are not canary-scoped, so a `.fleet.mk` pin can no longer silently validate prod secrets against canary hosts.

Execution plan: `plans/011-canary-secrets-scoping-guard.md`.

## Acceptance criteria

- Prod-scoped override: exit 2 refusal with actionable message, zero deploy side effects.
- Canary-scoped values pass the guard (recursion line reached under `make -n`).
- Only the `deploy-canary` recipe changed; `make -n check` parses clean.
