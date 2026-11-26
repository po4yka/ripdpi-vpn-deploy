---
id: OPS-1795702314418305
title: Preview several nodes at once while deploys stay serial
kind: feature
status: backlog
area: operations
priority: medium
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: ops-1795702314418305-concurrent-node-previews
created: 2026-11-26
updated: 2026-11-26
related_tasks: []
---

## Goal

Previews of different production nodes run at the same time from one worktree, so the preview phase of a rollout takes about as long as its slowest node instead of the sum of all nodes. Deploys stay one node at a time. The measurements and the shared-state analysis are in `docs/tasks/work/OPS-1795697141240057.md`.

## Acceptance criteria

- The deploy controller takes an exclusive per-node operation lock on the operator machine for each selected alias in `dry-run` and `deploy`, and refuses with `node-operation-in-progress` before any SSH operation when another run holds it.
- `deploy` also takes one fleet deploy lock and refuses with `deploy-in-progress` while another deploy runs; `dry-run` does not take it.
- The deploy runbook gives a recipe for concurrent previews: one clean worktree, one controller process per alias, a private `SECRETS_FILE` and an explicit `ANSIBLE_INVENTORY` for each, and one log for each.
- Two production aliases preview at the same time from one worktree, and their durations are recorded.
