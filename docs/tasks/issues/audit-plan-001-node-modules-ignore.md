---
id: CIC-1787495848053690
title: Ignore tools/tasking/node_modules in repo .gitignore
kind: bug
status: done
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
status_detail: Implementation and targeted regressions passed; exact-source hosted CI and final closure remain pending.
closed_at: "2026-08-27T14:12:46Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Repository-local ignore tests exclude tasking dependencies independently of global ignore settings. Implementation verified at 1221ccb59ae90f4d5d7fc3951018dcbef1634841: local make check passed (1055 pytest, one pre-existing network-scan skip, 55 Bats, 79 Terraform tests, 45 Conftest tests, 102 snapshots); hosted CI run 33079404315 passed all 51 jobs. Probe schema synchronization is a separate withheld task."
---

## Goal

Repository `.gitignore` ignores `tools/tasking/node_modules/` so a fresh clone can no longer commit the 80-package dependency tree by accident; exclusion no longer depends on one operator's global git config.

Execution plan: `plans/001-node-modules-gitignore.md` (self-contained handoff plan; follow its STOP conditions).

## Acceptance criteria

- `tools/tasking/node_modules/` ignored by the repo `.gitignore`; `git check-ignore -v` resolves to the repo rule, not `~/.config/git/ignore`.
- Unit contract test (`tests/unit/test_gitignore_contracts.py`) asserts the rule and passes.
