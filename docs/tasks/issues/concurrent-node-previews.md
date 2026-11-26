---
id: OPS-1795702314418305
title: Preview several nodes at once while deploys stay serial
kind: feature
status: done
area: operations
priority: medium
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: ops-1795702314418305-concurrent-node-previews
created: 2026-11-26
updated: 2026-11-27
related_tasks: []
status_detail: Concurrent previews of node-a and node-b passed from one worktree at e16a6a59e; live lock refusal recorded
closed_at: "2026-11-26T20:20:50Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Per-node and fleet deploy locks merged in PR 748 (main ci 45856572048 at e16a6a59e passed); concurrent previews of node-a (1040.5 s) and node-b (1382.7 s) from one worktree passed in 23 min 5 s; a third node-a preview was refused on its node lock
---

## Goal

Previews of different production nodes run at the same time from one worktree, so the preview phase of a rollout takes about as long as its slowest node instead of the sum of all nodes. Deploys stay one node at a time. The measurements and the shared-state analysis are in [the preview cost research](../../research/preview-cost-2026-11.md).

## Acceptance criteria

- The deploy controller takes an exclusive per-node operation lock on the operator machine for each selected alias in `dry-run` and `deploy`, and refuses with `node-operation-in-progress` before any SSH operation when another run holds it.
- `deploy` also takes one fleet deploy lock and refuses with `deploy-in-progress` while another deploy runs; `dry-run` does not take it.
- The deploy runbook gives a recipe for concurrent previews: one clean worktree, one controller process per alias, a private `SECRETS_FILE` and an explicit `ANSIBLE_INVENTORY` for each, and one log for each.
- Two production aliases preview at the same time from one worktree, and their durations are recorded.
