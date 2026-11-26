---
id: OPS-1795351496232576
title: Carry the ops repository capability and prove its inputs with a dry-run
kind: feature
status: done
area: operations
priority: high
risk: high
owner: Planner
parent: EPC-1795327697650892
blocked_by: []
spec_mode: required
openspec_change: ops-1795351496232576-private-ops-repository-evidence-w1b
created: 2026-11-22
updated: 2026-11-26
related_tasks: []
status_detail: Both steps done; W1 evidence and the node-c check through the ops inventory are recorded
closed_at: "2026-11-26T12:52:42Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: W1 evidence from pull requests 683 and 686 and the ops repository; node-c check through the ops inventory passed at d7a08417
---

## Goal

W1's private ops repository capability reaches the main specs with recorded evidence, and a check-mode dry-run through the ops inventory shows the same host selection and inputs as the kit. Replaces the dropped `OPS-1795327950629406`, whose lifecycle could not close after an invalid evidence transfer.

## Acceptance criteria

- Every carried requirement maps to recorded evidence from pull requests 683 and 686 and the ops repository.
- Authorized: a check-mode dry-run for `node-c` through the ops inventory selects the same host with the same inputs as the kit run.
- The change archives with spec sync into `openspec/specs/operations/private-ops-repository/`.
