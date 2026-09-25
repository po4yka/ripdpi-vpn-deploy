---
id: SCR-1790318637598901
title: Keep taskctl new fail-before-write when openspec is missing
kind: bug
status: review
area: scripts
priority: medium
risk: standard
owner: Primary agent
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-09-25
updated: 2026-09-25
spec_reason: tooling-only
related_tasks: []
---

## Goal

`./taskctl new --spec-mode required` resolves the pinned openspec binary before reserving a task ID or writing any portfolio record, so a missing `tools/tasking` install fails with no orphan `docs/tasks/issues/<slug>.md` that would break later `taskctl new` / `taskctl validate` runs and block a retry with the same slug.

## Acceptance criteria

- With `tools/tasking/node_modules/.bin/openspec` absent, `command_new` for a spec-required task fails with the missing-openspec error and leaves `docs/tasks/issues/` and `docs/tasks/work/` unchanged (regression test in `scripts/tests/test_taskctl.py`).
- `mise exec -- python3 -m pytest scripts/tests/test_taskctl.py -q` and `make task-check` pass.
