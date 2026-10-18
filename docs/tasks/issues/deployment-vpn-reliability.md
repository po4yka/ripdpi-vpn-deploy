---
id: OPS-1792263187492070
title: Restore deployment and VPN rollback reliability
kind: bug
status: doing
area: operations
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: deployment-vpn-reliability
created: 2026-10-17
updated: 2026-10-17
related_tasks: []
---

## Goal

Repair all six audited deployment and VPN recovery defects with regression coverage; merge the verified source fix without a live rollout.

## Acceptance criteria

- Dependent phases remain serial and dry-run intent is honored.
- State backups select the exact environment.
- Firewall and complete AWG runtime recover coherently after rejection.
- CI descendants cannot survive command cleanup.
- Focused regressions, applicable repository gates, review and exact-source CI pass before merge.
