---
id: CIC-1788708456909496
title: Make evidence ownership and closure links durable
kind: feature
status: review
area: ci
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: cic-1788708456909496-make-evidence-ownership-and-closure-links-durable
created: 2026-09-06
updated: 2026-09-06
related_tasks: []
status_detail: Source implementation and exact-head PR checks passed; protected-main integration remains the delivery boundary.
---

## Goal

Make proportional verification an executable task-lifecycle contract: every
evidence-policy change is owned by a tracked OpenSpec change, client traffic
requires client-layer proof, and an operational task can retain a validated
link to a completed source task after the source record is archived and purged.

## Acceptance criteria

- `taskctl` resolves retained local task references through committed terminal
  history after a valid two-commit purge, without accepting a dropped,
  uncommitted, malformed, or ambiguous historical task.
- Purging a completed source task preserves an incoming non-blocking evidence
  ownership link and still rejects unsafe parent or unresolved blocker edges.
- Proportional-evidence policy explicitly requires the `client` evidence layer
  for authenticated client traffic and is owned by this OpenSpec change.
- Focused regression tests cover valid history, missing history, dropped tasks,
  invalid latest incarnations, graph cycles, and dirty or incomplete terminal
  transitions.
- `./taskctl validate`, `make task-check`, and exact-head hosted required checks
  pass before the policy is used to close another task.

## Ownership

- Primary owns `scripts/tasks/taskctl.py`, its existing task-contract tests,
  task lifecycle documentation, and this task's OpenSpec artifacts.
- Existing Critical/High source and operational tasks remain open; this change
  cannot reclassify their required or blocked evidence.
