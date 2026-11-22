---
id: OPS-1795351496232576
title: Carry the ops repository capability and prove its inputs with a dry-run
kind: feature
status: backlog
area: operations
priority: high
risk: high
owner: Planner
parent: EPC-1795327697650892
blocked_by: []
spec_mode: required
openspec_change: ops-1795351496232576-private-ops-repository-evidence-w1b
created: 2026-11-22
updated: 2026-11-22
related_tasks: []
---

## Goal

W1's private ops repository capability reaches the main specs with recorded evidence, and a check-mode dry-run through the ops inventory shows the same host selection and inputs as the kit. Replaces the dropped `OPS-1795327950629406`, whose lifecycle could not close after an invalid evidence transfer.

## Acceptance criteria

- Every carried requirement maps to recorded evidence from pull requests 683 and 686 and the ops repository.
- Authorized: a check-mode dry-run for `node-c` through the ops inventory selects the same host with the same inputs as the kit run.
- The change archives with spec sync into `openspec/specs/operations/private-ops-repository/`.
