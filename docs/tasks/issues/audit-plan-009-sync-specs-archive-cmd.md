---
id: CIC-1787495859628443
title: Point sync-specs skill at the supported archive command
kind: bug
status: done
area: ci
priority: medium
risk: standard
owner: unassigned
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-23
updated: 2026-09-09
spec_reason: docs-only
related_tasks: []
closed_at: "2026-09-09T02:28:48Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Local gates: make ci-fast targets green in the worktree (actionlint, zizmor, cloud-init schema, tf-test, tf-policy, yamllint, shellcheck, vpnd-deny, MSRV, 139 golden snapshots, secrets schema, bundle contract, full bats suite, vpnd clippy -D warnings and debug/release tests); make validate green; taskctl validate + make task-check green. Remote CI: exact-main ci.yml run on 2c5544fe20471bc43c649aef2278e3efe34503b6 merged via PR #211 with all pytest groups, codeql and required checks green."
---

## Goal

The generated `openspec-sync-specs` skill references the supported `./taskctl openspec archive` command instead of the rejected `openspec cli archive` passthrough, so agents no longer hit a hard stop mid-workflow; the generated-assets lock stays tamper-evident and green.

Execution plan: `plans/009-sync-specs-archive-command.md`.

## Acceptance criteria

- Zero `openspec cli archive` references remain under `.agents/skills/`.
- `generated-assets.lock.json` hash for the skill updated; JSON parses.
- `./taskctl validate` and `make task-check` exit 0.
