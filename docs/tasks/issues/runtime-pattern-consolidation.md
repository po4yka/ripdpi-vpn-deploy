---
id: ANS-1787497148207353
title: Consolidate duplicated runtime patterns across roles
kind: chore
status: dropped
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
related_tasks: []
closed_at: "2026-09-06T17:42:11Z"
closed_reason: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed.
evidence_summary: Owner-authorized cancellation only. Existing implementation is retained; no staging, live, client, provider or operational acceptance success is claimed. Prior evidence remains in Git history.
---

## Goal

Each duplicated runtime concern collapses onto one contract-tested implementation: shared release installation with rollback support on all six consumers, one source-build receipt idiom, a leveled hardening floor for the Ansible-owned units in this change, validate-before-restart plus liveness waits on every in-scope service role, single-sourced listener port defaults and P0 shape contract, one validated nftables policy idiom, checker-owned collision defense, activation-safe cascade scaffolds, and asserted mirror restore layout. See openspec/changes/ans-1787497148207353-runtime-pattern-consolidation/.

## Acceptance criteria

- All thirteen execution steps in the linked change are checked with staged per-consumer evidence.
- Rendered-config snapshot parity holds where behavior is intended unchanged; new capabilities covered by their own tests.
- `make ci-fast` and `make validate` green on the final SHA after the last migration commit.
