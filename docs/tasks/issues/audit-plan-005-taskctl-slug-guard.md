---
id: CIC-1787495848625122
title: Reject path-traversal values in taskctl new slug flag
kind: bug
status: backlog
area: ci
priority: medium
risk: standard
owner: unassigned
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-23
updated: 2026-08-23
spec_reason: regression-tested-single-module
related_tasks: []
---

## Goal

`./taskctl new` rejects `--slug` values that could escape the portfolio directory (absolute paths, `..`, slashes) with a clear fail-closed error before any filesystem write outside `docs/tasks/issues/`.

Execution plan: `plans/005-taskctl-slug-validation.md`.

## Acceptance criteria

- Traversal probes (`../evil`, absolute path) exit 2 with zero side effects outside a temp root.
- Happy-path creation inside a temp root still works; `./taskctl validate` stays green.

