---
id: CIC-1788741692326070
title: Require committed review before terminal close
kind: bug
status: doing
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
status_detail: "Addressing PR #189 review findings: OpenSpec ownership, committed-review archive sequencing, and bounded selected-record lookup."
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
