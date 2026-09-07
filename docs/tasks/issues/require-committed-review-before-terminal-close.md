---
id: CIC-1788741692326070
title: Require committed review before terminal close
kind: bug
status: done
area: ci
priority: critical
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: cic-1788741692326070-require-committed-review-before-terminal-close
created: 2026-09-07
updated: 2026-09-07
related_tasks: []
status_detail: "Exact source a13281ee passed full local gate and PR #189 CI 34096871763 (75/75) plus CodeQL 34096871547 (2/2, no current findings); ready for committed-review replay."
closed_at: "2026-09-07T08:39:08Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Protected main e20abbaddf9c4978025af2bf704897492ea91a28 passed CI 34099380224 (75/75), CodeQL 34099379996 (2/2), Scorecard 34099379941, and release-please 34099379820; archive-ready replay passed from committed review evidence 9dde8dd5.
---

## Goal

Prevent `taskctl close prepare --outcome done` from creating a terminal
snapshot unless the same task already has a committed `review` snapshot at
`HEAD`.

## Acceptance criteria

- Done closure refuses an uncommitted working-tree transition from `doing` to
  `review` without mutating the task or creating a close receipt.
- Done closure continues to accept a task whose `review` state is committed,
  preserving the existing two-commit terminal and purge lifecycle.
- The taskctl regression suite, repository task validation, and protected-main
  required checks pass.
