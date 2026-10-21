---
id: ANS-1792499727513191
title: Repair deployment readiness runtime defects
kind: bug
status: done
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
closed_at: "2026-10-21T08:22:01Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Accepted protected main 86d76430707a0e6febedaf4c7c8c19351b224d36 has the same tree as PR #347 head c1c5828b. PR CI 39543684353 and 39549714130 and main CI 39557145005 passed all 92 jobs, including Molecule, native lanes and the liveness parser check. Each finding has a regression that fails on its parent. No deployment."
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
