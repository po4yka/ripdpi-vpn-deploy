---
id: CIC-1787495848625122
title: Reject path-traversal values in taskctl new slug flag
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
spec_reason: regression-tested-single-module
related_tasks: []
closed_at: "2026-09-09T02:28:48Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Local gates: make ci-fast targets green in the worktree (actionlint, zizmor, cloud-init schema, tf-test, tf-policy, yamllint, shellcheck, vpnd-deny, MSRV, 139 golden snapshots, secrets schema, bundle contract, full bats suite, vpnd clippy -D warnings and debug/release tests); make validate green; taskctl validate + make task-check green. Remote CI: exact-main ci.yml run on 2c5544fe20471bc43c649aef2278e3efe34503b6 merged via PR #211 with all pytest groups, codeql and required checks green."
---

## Goal

`./taskctl new` rejects `--slug` values that could escape the portfolio directory (absolute paths, `..`, slashes) with a clear fail-closed error before any filesystem write outside `docs/tasks/issues/`.

Execution plan: `plans/005-taskctl-slug-validation.md`.

## Acceptance criteria

- Traversal probes (`../evil`, absolute path) exit 2 with zero side effects outside a temp root.
- Happy-path creation inside a temp root still works; `./taskctl validate` stays green.
