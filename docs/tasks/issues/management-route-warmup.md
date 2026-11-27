---
id: SCR-1795774108061951
title: Warm the Tailnet management route before readiness and outlast relay home changes
kind: feature
status: doing
area: scripts
priority: high
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: scr-1795774108061951-management-route-warmup
created: 2026-11-27
updated: 2026-11-27
related_tasks: []
---

## Goal

A preview or deploy over the relayed Tailnet route survives a change of the operator's home relay region and stops in seconds when the route cannot carry it. The [management route stalls research](../../research/management-route-stalls-2026-11.md) (`OPS-1795702284251279`) found that the controller's 15 s readiness probe can run before the relay path is connected, and that a node keeps replying through the operator's previous relay region for up to about 117 s, close to the 120 s budget of the shared SSH master.

## Acceptance criteria

- Before its readiness probe, a `dry-run` or `deploy` on a Tailnet transport sends one warm-up probe that waits up to 30 s and refuses with `management-route-unreachable` without a reply, then measures the route with the existing ten-probe gate; the CI handoff run and public transports stay unprobed.
- The shared SSH master uses `ServerAliveInterval=15` and `ServerAliveCountMax=20` in both modes, Ansible SSH retries stay disabled, and the strict readiness and lockout commands are unchanged.
- The deploy runbook names the refusal categories and the gated preview, and `REQ-OPS-CHANNEL-GATE` and `REQ-OPS-CHANNEL-SESSION` of `scr-1795082568279731-deploy-slow-channel-tolerance` are reconciled before either change is archived.
- A timed preview of one production node over the relayed route passes the warm-up and the measurement.
