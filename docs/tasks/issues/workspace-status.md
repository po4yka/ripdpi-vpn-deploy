---
id: SCR-1791023422420637
title: Expose local checkout provenance before documentation discovery
kind: chore
status: doing
area: scripts
priority: medium
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-10-03
updated: 2026-10-03
spec_reason: tooling-only
related_tasks: []
---

## Goal

Expose a compact, read-only checkout summary before agents search documentation,
so branch/worktree drift is visible and subagent handoffs carry the selected source.

## Acceptance criteria

- The documented sanitized `make workspace-status` entry reports cwd, worktree,
  branch/detached HEAD, exact SHA,
  ahead/behind known local `origin/main`, and staged/unstaged/untracked counts.
- Discovery performs no fetch, index refresh, fleet configuration parsing,
  provider access, secret reads or workspace mutation; missing main is explicit.
- Optional `--task <TASK-ID> --json` resolves portfolio/execution/change pointers
  through `taskctl`; a bad selected task fails without printing its document.
- Real Git regression tests, instruction checks, `make check` and exact-source
  hosted checks pass; the implementation is delivered on protected `main`.
