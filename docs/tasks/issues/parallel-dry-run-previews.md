---
id: OPS-1795697141240057
title: Measure dry-run task cost and design parallel per-node previews
kind: research
status: backlog
area: operations
priority: medium
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-11-26
updated: 2026-11-26
spec_reason: research-only
related_tasks: []
---

## Goal

A full-graph `make dry-run ANSIBLE_LIMIT='<exact-alias>' ANSIBLE_TAGS=` against one production node takes 25 to 57 minutes, and a five-node rollout previews each node in turn, so the preview phase alone takes several hours. The 2026-11-26 rollout of d7a08417 showed about 1300 tasks per node (about 750 ok, about 560 skipped), with `runtime-release` (about 260 tasks, included by about 49 consumer entry points), `firewall`, `nginx-xhttp`, `baseline` and `transport-egress` as the largest roles. Skipped tasks and controller-local facts do not explain the duration, and the log records no per-task timing, so the slow tasks are unknown.

This research names the tasks that dominate preview time and gives a decided design for running previews of different nodes at the same time. Deploys stay serial: `site.yml` keeps `serial: 1` and each node keeps its `transaction.lock`.

## Acceptance criteria

- A timed preview of at least one core node and one split-hop node (for example with `ANSIBLE_CALLBACKS_ENABLED=ansible.posix.profile_tasks`) lists the 20 slowest tasks, their role, and whether each one makes a remote call in check mode.
- Each slow task gets a decision: keep, make cheaper (for example run a repeated `runtime-release` check once per play), or skip in check mode, with the reason. The decision does not weaken a recovery, security or authority gate.
- The design states which shared local state blocks concurrent previews from one checkout (at least the canonical `ansible/inventory/generated.ini` copy, the SSH ControlMaster path and the plaintext secrets path) and how each concurrent preview gets its own copy, for example one worktree per node at the same revision.
- The design states that only previews run concurrently, and that `deploy`, `verify` and later stages stay one node at a time.
- Follow-up tasks exist for each change the design selects; a change to deployment lifecycle behaviour gets `spec_mode: required`.
