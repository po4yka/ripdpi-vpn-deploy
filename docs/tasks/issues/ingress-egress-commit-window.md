---
id: ANS-1791996786767919
title: Close the window between protected ingress commit and egress finish
kind: bug
status: review
area: ansible
priority: medium
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1791996786767919-ingress-egress-commit-window
created: 2026-10-14
updated: 2026-10-16
related_tasks: []
status_detail: Local gate and all native commit-boundary cases passed; awaiting final protected CI aggregation.
---

## Goal

A deploy interrupted between protected ingress `--site commit` and egress outer `finish` (`ansible/playbooks/tasks/transport-ingress-commit.yml`) no longer leaves ingress and egress at different accepted generations: the next run completes or restores both as one boundary. Found while re-verifying audit finding H1 on 2026-10-14; depends on ANS-1791996027408136.

## Acceptance criteria

- SIGKILL at every commit boundary is followed by a run that leaves ingress and egress at one accepted generation.
- Requirement REQ-OPS-ORP-COMMIT-ATOMIC maps to passing evidence in the change verification.
