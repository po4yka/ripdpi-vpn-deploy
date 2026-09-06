---
id: TST-1788679651303079
title: Run full-stack CI scenarios in parallel matrix jobs
kind: chore
status: doing
area: testing
priority: medium
risk: standard
owner: unassigned
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-09-06
updated: 2026-09-06
spec_reason: tooling-only
related_tasks: []
---

## Goal

Run the full-stack and full-stack-published Molecule scenarios concurrently on
separate hosted runners to shorten feedback for cross-role convergence changes.

## Acceptance criteria

- Both scenarios run exactly once as separate matrix jobs, with fail-fast disabled.
- Required checks fail if either scenario fails; scenario sequences stay intact.
- Workflow checks and affected regression tests pass; hosted CI verifies both jobs.
