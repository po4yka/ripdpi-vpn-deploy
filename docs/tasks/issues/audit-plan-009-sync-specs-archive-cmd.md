---
id: CIC-1787495859628443
title: Point sync-specs skill at the supported archive command
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
spec_reason: docs-only
related_tasks: []
---

## Goal

The generated `openspec-sync-specs` skill references the supported `./taskctl openspec archive` command instead of the rejected `openspec cli archive` passthrough, so agents no longer hit a hard stop mid-workflow; the generated-assets lock stays tamper-evident and green.

Execution plan: `plans/009-sync-specs-archive-command.md`.

## Acceptance criteria

- Zero `openspec cli archive` references remain under `.agents/skills/`.
- `generated-assets.lock.json` hash for the skill updated; JSON parses.
- `./taskctl validate` and `make task-check` exit 0.

