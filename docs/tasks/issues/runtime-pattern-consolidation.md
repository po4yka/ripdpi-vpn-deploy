---
id: ANS-1787497148207353
title: Consolidate duplicated runtime patterns across roles
kind: chore
status: done
area: ansible
priority: medium
risk: high
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1787497148207353-runtime-pattern-consolidation
created: 2026-08-23
updated: 2026-09-06
related_tasks: [ANS-1787463116251274]
status_detail: Runtime consumers, validators, unit floors, shared templates and restore guards are integrated through PR 167 with protected-main checks. Shared external acceptance is consolidated in OPS-1787496414433523 and TST-1787850553468536.
closed_at: "2026-09-06T13:56:47Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Runtime consolidation and consumer migration passed PR 167 and protected-main checks; shared external acceptance remains in OPS-1787496414433523 and TST-1787850553468536.
---

## Goal

Each duplicated runtime concern collapses onto one contract-tested implementation: shared release installation with rollback support on all six consumers, one source-build receipt idiom, a leveled hardening floor for the Ansible-owned units in this change, validate-before-restart plus liveness waits on every in-scope service role, single-sourced listener port defaults and P0 shape contract, one validated nftables policy idiom, checker-owned collision defense, activation-safe cascade scaffolds, and asserted mirror restore layout. See openspec/changes/ans-1787497148207353-runtime-pattern-consolidation/.

## Acceptance criteria

- All thirteen execution steps in the linked change are checked with staged per-consumer evidence.
- Rendered-config snapshot parity holds where behavior is intended unchanged; new capabilities covered by their own tests.
- `make ci-fast` and `make validate` green on the final SHA after the last migration commit.
