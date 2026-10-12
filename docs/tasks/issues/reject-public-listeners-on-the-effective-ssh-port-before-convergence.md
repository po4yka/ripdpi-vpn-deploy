---
id: ANS-1790316250156031
title: Reject public listeners on the effective SSH port before convergence
kind: bug
status: done
area: ansible
priority: medium
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1790316250156031-reject-public-listeners-on-the-effective-ssh-port-before-convergence
created: 2026-09-25
updated: 2026-10-12
related_tasks: []
status_detail: Accepted integrated runtime source cf01f94a640913412f3316b5cb288881639712ce passed all 86 protected-main jobs in run 38134843683. Recorded verification results and external scope qualifications are preserved.
closed_at: "2026-10-11T22:09:35Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Integrated runtime source cf01f94a640913412f3316b5cb288881639712ce passed all 86 protected-main jobs in run 38134843683. Recorded requirement-specific verification and external qualifications are preserved. Complete local gate components passed: 6,340 portable tests, 22 subtests, 297 CLI tests, 206 baseline transfers and 57 shell tests. Every assertion and deadline is retained; production code is unchanged."
---

## Goal

Firewall convergence fails closed when any TCP public listener contract entry, including the honeypot, claims the effective `sshd -T` port, so the contract loop can never open SSH to every source.

## Acceptance criteria

- An exact TCP port or TCP port range covering the effective SSH port fails the firewall role before its first mutation and before nftables renders, naming the listener and port.
- UDP listeners on the same port number and non-overlapping TCP listeners pass unchanged.
- The check is not suppressible by `listener_collision_allowlist` and runs in check mode.
- Unit tests under `tests/unit/` evaluate the real firewall task with the pinned ansible-core templar.
- The honeypot pitfall no longer says nothing checks the SSH port.
