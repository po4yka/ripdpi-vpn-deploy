---
id: CIC-1788684721834869
title: Select CI checks from changed-file dependencies
kind: chore
status: doing
area: ci
priority: high
risk: standard
owner: Codex
parent: null
blocked_by: []
spec_mode: required
openspec_change: cic-1788684721834869-ci-dependency-selection
created: 2026-09-06
updated: 2026-09-06
related_tasks: []
---

## Goal

Select costly PR checks using the transitive consumers of changed files, while
keeping full checks on main pushes and manual runs. Preserve mandatory coverage
and reject any skip that the dependency plan did not explicitly authorize.

## Acceptance criteria

- Changes select their complete consumer groups, including docs embedded by Rust,
  Ansible native/image dependencies, shared fixtures and configuration fan-out.
- Unknown paths, invalid/unavailable history and empty diffs select all checks.
  Renames and deletions retain the original paths; selection uses the whole PR.
- Pytest, Python validators, task contracts and static/security lint always run.
  Selected checks must succeed; only explicitly unselected checks may be skipped.
- All existing commands and matrix entries remain executable. Main and manual
  runs execute the complete graph. Tests cover selection, history and gate errors.
- Branch protection is migrated only after a green full PR run; its strict mode,
  app bindings and unrelated settings remain intact. Observe a selective hosted
  run, deliver through protected main and verify the pushed revision's full CI.
