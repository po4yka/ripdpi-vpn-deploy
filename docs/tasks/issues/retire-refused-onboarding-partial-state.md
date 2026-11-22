---
id: OPS-1795351418267220
title: Retire a refused-onboarding partial staging state through unbound retirement
kind: bug
status: doing
area: operations
priority: medium
risk: high
owner: unassigned
parent: null
blocked_by: []
spec_mode: required
openspec_change: ops-1795351418267220-retire-refused-onboarding-partial-state
created: 2026-11-22
updated: 2026-11-22
related_tasks: []
---

## Goal

A disposable staging run whose onboarding refused after finalization wrote its authority, liveness config and executor manifest copy retires through `make retire-unbound-staging-client` and `make retire-unbound-staging-executor` after verified provider absence, with no hand-moved files and no fabricated binding.

## Acceptance criteria

- The exact refused-onboarding prefix retires both client and prepared executor; the partial outputs stay in place and their digests are in the journaled request.
- A binding, registry, pending registry, promotion config, profile assignment record, a gap in the write order or foreign content refuses with `retirement-bound` before any mutation.
- A changed partial output refuses resume; nothing is published from a changed request.
- The runbook, cleanup skill and design notes describe the path; `make check` passes.
