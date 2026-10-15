---
id: ANS-1792073622616697
title: Close runtime helper files and clear CodeQL findings
kind: bug
status: done
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
status_detail: "All 59 alerts reviewed; CodeQL reports zero findings and focused regressions pass. PR #300 carries full-gate and hosted runtime evidence; no live actions."
closed_at: "2026-10-15T16:25:34Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Integrated PR 300 source 923304729f6bdd32edce6a9b6ceada1d51c7d011 passed CI 38759230876 and CodeQL 38759230898; current open CodeQL alert count is zero. Full native runtime acceptance passed 4 cases, native integration 138; targeted recovery suite passed 517. Descriptor lifetime and cleanup contracts retained.
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
