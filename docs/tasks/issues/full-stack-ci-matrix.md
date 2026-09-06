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
status_detail: Both hosted matrix jobs passed on b4cdc0da; 14 targeted tests and workflow/pre-commit checks passed.
closed_at: "2026-09-06T07:38:07Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Implementation b4cdc0da7e3ecb060961fbdfb1fde3c59ca5040b: 14 affected tests passed, actionlint/zizmor/pre-commit passed. Hosted CI run 34019345569: full-stack and full-stack-published both passed on separate runners, starting together at 07:30:41Z and completing at 07:37:13Z and 07:36:47Z. The required aggregator retains the matrix dependency."
---

## Goal

Run the full-stack and full-stack-published Molecule scenarios concurrently on
separate hosted runners to shorten feedback for cross-role convergence changes.

## Acceptance criteria

- Both scenarios run exactly once as separate matrix jobs, with fail-fast disabled.
- Required checks fail if either scenario fails; scenario sequences stay intact.
- Workflow checks and affected regression tests pass; hosted CI verifies both jobs.
