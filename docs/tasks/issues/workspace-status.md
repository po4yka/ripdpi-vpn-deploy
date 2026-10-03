---
id: SCR-1791023422420637
title: Expose local checkout provenance before documentation discovery
kind: chore
status: done
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
status_detail: Implementation and independent review complete; local full gate and final focused tests passed; exact-source hosted checks and protected-main integration pending.
closed_at: "2026-10-03T14:21:18Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Delivered on protected main c8cb570d86ecb87d7f418692d1297a7645ec00b3 with tree identical to tested source 1d748265ff261af678ff6a21c2f9ebfead1ae539. Exact-source CI 37128061697 succeeded, selected PR checks passed, independent review approved, local make check and final focused 39 tests passed. Canonical discovery and task validation on main passed.
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
