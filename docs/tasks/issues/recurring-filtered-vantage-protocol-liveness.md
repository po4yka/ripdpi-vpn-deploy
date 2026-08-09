---
id: MON-1786299441667649
title: Make filtered-vantage protocol liveness a recurring fleet gate
kind: feature
status: backlog
area: monitoring
priority: high
risk: high
owner: Protocol liveness
parent: null
blocked_by: []
spec_mode: required
openspec_change: mon-1786299441667649-recurring-filtered-vantage-protocol-liveness
created: 2026-08-09
updated: 2026-08-09
related_tasks: []
---

## Goal

Promote the existing multi-vantage liveness design into a recurring fleet gate
that distinguishes server failure, filtered-path failure, unavailable evidence,
and stale evidence for every supported logical profile.

## Ownership

- Primary surfaces: protocol-liveness policy/evaluator, sentinel scheduling,
  redacted evidence, alerting, focused tests, and operator documentation.
- Serialized lanes: shared liveness schema, operator schedule, and rotation
  candidate state have one writer at a time.

## Acceptance criteria

- Every supported logical profile is exercised from at least two independent
  access-path classes with an unfiltered control.
- Server-side failure, filtered-path failure, unknown, and stale evidence remain
  separate and cannot be promoted into each other.
- Rotation candidacy requires sustained quorum evidence; promotion remains
  explicit and cannot occur automatically.
- Recurring evidence is redacted, freshness-bound, and observed through failure,
  recovery, and one unavailable-vantage case.
- Current fleet status records the exact verification boundary without claiming
  client-path proof from listener or local health.

## Verification

- `make task-check`
- Focused liveness evaluator, sentinel, alerting, and rotation tests
- Staging failure/recovery drill and a recurring fleet observation
