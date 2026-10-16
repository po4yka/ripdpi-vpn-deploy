---
id: ANS-1791996786767919
title: Close the window between protected ingress commit and egress finish
kind: bug
status: done
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
status_detail: Full local gate, all native commit boundaries and exact-source protected CI passed.
closed_at: "2026-10-16T17:26:18Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Source 8f89764ab5c3bfc38224f948ef4b54c59cd16465: full gated make check passed; all 12 native transport cases including six SIGKILL boundaries passed; CI run 38930926508 and required-checks job 117092904845 succeeded; both CodeQL alerts fixed and review threads resolved."
---

## Goal

A deploy interrupted between protected ingress `--site commit` and egress outer `finish` (`ansible/playbooks/tasks/transport-ingress-commit.yml`) no longer leaves ingress and egress at different accepted generations: the next run completes or restores both as one boundary. Found while re-verifying audit finding H1 on 2026-10-14; depends on ANS-1791996027408136.

## Acceptance criteria

- SIGKILL at every commit boundary is followed by a run that leaves ingress and egress at one accepted generation.
- Requirement REQ-OPS-ORP-COMMIT-ATOMIC maps to passing evidence in the change verification.
