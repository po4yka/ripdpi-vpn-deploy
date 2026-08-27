---
id: CIC-1787495848053690
title: Ignore tools/tasking/node_modules in repo .gitignore
kind: bug
status: doing
area: ci
priority: high
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-23
updated: 2026-08-27
spec_reason: test-only
related_tasks: []
---

## Goal

Repository `.gitignore` ignores `tools/tasking/node_modules/` so a fresh clone can no longer commit the 80-package dependency tree by accident; exclusion no longer depends on one operator's global git config.

Execution plan: `plans/001-node-modules-gitignore.md` (self-contained handoff plan; follow its STOP conditions).

## Acceptance criteria

- `tools/tasking/node_modules/` ignored by the repo `.gitignore`; `git check-ignore -v` resolves to the repo rule, not `~/.config/git/ignore`.
- Unit contract test (`tests/unit/test_gitignore_contracts.py`) asserts the rule and passes.
