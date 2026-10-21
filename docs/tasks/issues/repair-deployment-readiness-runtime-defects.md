---
id: ANS-1792499727513191
title: Repair deployment readiness runtime defects
kind: bug
status: review
area: ansible
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1792499727513191-repair-deployment-readiness-runtime-defects
created: 2026-10-20
updated: 2026-10-21
related_tasks: []
---

## Goal

Production profiles converge without a daily Xray outage from log rotation,
without removing the host resolver on Debian 13, without AWG reach into
private or metadata destinations, without watchdog restarts after failed
configuration validation, and without pre-release Hysteria pins.

## Acceptance criteria

- Each audited defect has a regression that fails on the parent commit.
- Focused tests, snapshots, task validation and `make check` pass.
- An independent review of the exact patch reports no unresolved defect.
