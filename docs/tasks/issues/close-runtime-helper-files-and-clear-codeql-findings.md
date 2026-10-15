---
id: ANS-1792073622616697
title: Close runtime helper files and clear CodeQL findings
kind: bug
status: doing
area: ansible
priority: medium
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-10-15
updated: 2026-10-15
spec_reason: mechanical-refactor
related_tasks: []
---

## Goal

Review all 59 open CodeQL alerts from the 2026-10-15 snapshot, make directory
descriptor ownership explicit, and repair remaining quality findings without
changing runtime publication, readiness or compensation contracts.

## Acceptance criteria

- Account for all 59 alerts, including findings already repaired on main.
- Retain trusted directory descriptors until transaction exit and close them on
  successful, exceptional, interrupted and failed-entry paths.
- Preserve native validator and process cleanup behavior while resolving the
  remaining import, unused-variable, mixed-return and empty-except findings.
- Pass focused portable regressions and the complete local gate; prepare a PR
  and verify its CodeQL result. Native Linux checks remain explicit CI evidence.
