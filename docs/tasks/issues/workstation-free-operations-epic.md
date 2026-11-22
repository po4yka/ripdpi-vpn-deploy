---
id: EPC-1795327697650892
title: Operate the VPN service without the operator workstation
kind: epic
status: backlog
area: epic
priority: high
risk: high
owner: Planner
parent: null
blocked_by: []
spec_mode: required
openspec_change: epc-1795327697650892-workstation-free-operations-epic
created: 2026-11-22
updated: 2026-11-22
related_tasks: []
---

## Goal

A Claude cloud session with no secrets, the private ops repository CI and one dedicated egress VPS can deploy the whole VPN service and change any operational setting while the operator MacBook is off. Children W1 to W7 deliver it in dependency order.

## Acceptance criteria

- W1 to W7 are done with their verification files complete.
- `./taskctl graph` shows the blocked_by edges of `REQ-WFO-ORDER`.
- A workstation-off drill receipt shows a cloud-session pull request change a non-secret setting and CI plan, apply, dry-run, deploy, verify and issue one device.
- The MacBook break-glass path works against the same remote state and ops repository.
