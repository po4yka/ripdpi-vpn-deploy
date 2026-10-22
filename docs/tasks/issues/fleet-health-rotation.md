---
id: OPS-1792654666090980
title: Repair fleet health and resumable rotation boundaries
kind: bug
status: done
area: operations
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: fleet-health-rotation
created: 2026-10-22
updated: 2026-10-22
related_tasks: []
closed_at: "2026-10-22T11:45:41Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Merged PR 356 at 37939d5a; complete local make check and 224 integration tests passed. Exact-main CI 39761736896 and CodeQL 39761737020 passed all required checks. No live infrastructure operation was performed.
---

## Goal

Make fleet status truthful and strictly inventory-bound, enforce authenticated
survivor availability during rotation, and resume only the exact reviewed plan.

## Acceptance criteria

- Fleet status preserves pinned inventory SSH identity and reports failed,
  stale or absent watchdog results without equating TCP/443 with VPN health.
- Rotation counts only distinct surviving nodes with fresh authenticated
  evidence for every required protocol; missing or invalid evidence refuses.
- Changed plans, unsafe or malformed progress, concurrent runs and uncertain
  interrupted steps cannot skip or repeat an external operation automatically.
- Successful step-boundary resume works and preserves exact progress.
- Regression tests, required local checks, independent review, PR checks and
  exact-revision protected-main checks pass without live infrastructure access.
