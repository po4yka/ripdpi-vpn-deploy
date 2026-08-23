---
id: ANS-1787497148207353
title: Consolidate duplicated runtime patterns across roles
kind: chore
status: backlog
area: ansible
priority: medium
risk: high
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1787497148207353-runtime-pattern-consolidation
created: 2026-08-23
updated: 2026-08-23
related_tasks: ["ANS-1787463116251274"]
---

## Goal

Each duplicated runtime concern collapses onto one contract-tested implementation: shared release installation with rollback support on all six consumers, one source-build receipt idiom, leveled unit hardening floor fleet-wide, validate-before-restart plus liveness waits on every service role, single-sourced listener port defaults and P0 shape contract, one validated nftables policy idiom, checker-owned collision defense, activation-safe cascade scaffolds, and asserted mirror restore layout. See openspec/changes/ans-1787497148207353-runtime-pattern-consolidation/.

## Acceptance criteria

- All fourteen execution steps in the linked change are checked with staged per-consumer evidence.
- Rendered-config snapshot parity holds where behavior is intended unchanged; new capabilities covered by their own tests.
- `make ci-fast` and `make validate` green on the final SHA after the last migration commit.
