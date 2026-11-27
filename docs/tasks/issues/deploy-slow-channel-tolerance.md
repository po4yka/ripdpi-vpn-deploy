---
id: SCR-1795082568279731
title: Tolerate a slow operator channel during deploy
kind: feature
status: doing
area: scripts
priority: high
risk: high
owner: unassigned
parent: null
blocked_by: []
spec_mode: required
openspec_change: scr-1795082568279731-deploy-slow-channel-tolerance
created: 2026-11-19
updated: 2026-11-19
related_tasks: []
---

## Goal

A short stall of the operator channel no longer fails an Ansible task during a deploy, and a deploy over a lossy, slow or unmeasured Tailnet management route refuses before that node changes instead of failing inside the protected transaction.

## Acceptance criteria

- The shared Ansible SSH master uses `ServerAliveInterval=15`, `ServerAliveCountMax=20` (8 until `SCR-1795774108061951`) and `ConnectionAttempts=3`; readiness, recovery and fresh lockout proofs keep the strict single-attempt command.
- Controller-driven playbook hosts get `ansible_ssh_timeout=90` and no Ansible SSH retries.
- A deploy to a Tailnet address refuses with `management-route-lossy`, `management-route-slow` or `management-route-unmeasured` before the source recheck and playbook; since `SCR-1795774108061951` a dry-run is probed the same way, and the CI handoff run and other transports are not probed.
- `tests/unit/test_deploy_controller.py` covers the options, the timeout and every gate decision, and `docs/how-to/deploy.md` documents the refusals.
