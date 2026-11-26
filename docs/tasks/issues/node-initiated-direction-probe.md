---
id: MON-1795705539639667
title: Probe node-initiated connections from the liveness sentinel to separate one-way from two-way blocks
kind: feature
status: backlog
area: monitoring
priority: medium
risk: standard
owner: Planner
parent: null
blocked_by: [MON-1795086175387484]
spec_mode: required
openspec_change: mon-1795705539639667-node-initiated-direction-probe
created: 2026-11-26
updated: 2026-11-26
related_tasks: []
---

## Goal

The sentinel path also tests connections that the node starts toward domestic targets. Block detection (D5) can then tell "unreachable for clients only" from "blocked both ways".

## Acceptance criteria

- A node-side probe reports the result of connections that the node starts toward a configured set of domestic targets, by stage (connect, TLS).
- The result carries a direction label and feeds the D5 rotation hint text.
- Rotation semantics in `fleet-health-rotation` do not change.
- Probe traffic is bounded in rate and target count, and carries no client data.
