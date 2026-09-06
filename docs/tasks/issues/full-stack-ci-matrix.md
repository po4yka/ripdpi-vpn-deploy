---
id: TST-1788679651303079
title: Run full-stack CI scenarios in parallel matrix jobs
kind: chore
status: done
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
status_detail: Both matrix scenarios passed in hosted CI run 34019345569 on b4cdc0da; full CI and 14 affected local tests passed.
closed_at: "2026-09-06T07:43:19Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Full hosted CI run 34019345569 passed on b4cdc0da7e3ecb060961fbdfb1fde3c59ca5040b. Both matrix jobs started at 07:30:41Z; full-stack passed at 07:37:13Z and full-stack-published at 07:36:47Z. Local evidence: 14 tests, actionlint, zizmor and pre-commit passed; required checks retain the matrix dependency."
---

## Goal

Run the full-stack and full-stack-published Molecule scenarios concurrently on
separate hosted runners to shorten feedback for cross-role convergence changes.

## Acceptance criteria

- Both scenarios run exactly once as separate matrix jobs, with fail-fast disabled.
- Required checks fail if either scenario fails; scenario sequences stay intact.
- Workflow checks and affected regression tests pass; hosted CI verifies both jobs.
