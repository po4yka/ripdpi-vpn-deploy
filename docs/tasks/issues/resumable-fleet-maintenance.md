---
id: OPS-1793686022000048
title: Deliver resumable fleet maintenance and verified operator recovery
kind: feature
status: doing
area: operations
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: resumable-fleet-maintenance
created: 2026-11-03
updated: 2026-11-03
related_tasks: []
---

## Goal

Deliver resumable existing-node maintenance, complete release input validation
and verified private operator recovery. Then connect serial rollout, restore
checks, passive drift checks, bounded address maintenance, real engine CI and
routine credential separation to those commands.

## Acceptance criteria

- All ten requirements in the linked change have observed behavior tests.
- Required local and exact-revision hosted checks pass, with environment limits
  recorded separately from actual source failures.
- Source changes are reviewed and merged; required existing-host changes pass
  canonical preview, rollout and scoped live acceptance.
- Private configurations and recovery reflect the accepted runtime, and the
  offsite encrypted operator kit passes independent download and manifest checks.
