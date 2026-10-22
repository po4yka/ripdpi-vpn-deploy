---
id: SCR-1792659157802819
title: Deliver payload-verified failover and explicit alternate listeners
kind: feature
status: review
area: scripts
priority: high
risk: high
owner: codex
parent: null
blocked_by: []
spec_mode: required
openspec_change: scr-1792659157802819-payload-verified-failover
created: 2026-10-22
updated: 2026-10-22
related_tasks: ["po4yka/RIPDPI#TRN-1792659369802828"]
status_detail: Both payload-probe review defects are corrected and all 70 probe regressions pass; complete local and hosted acceptance remain required.
---

## Goal

Deliver trustworthy payload probes, coordinated recipient failover based on useful
traffic, and explicit alternate REALITY listeners without changing live nodes.

## Acceptance criteria

- A short, empty, incorrect or oversized successful HTTP response never passes a
  requested payload transfer; real local sockets exercise positive and negative paths.
- The supported RIPDPI recipient consumes bounded payload verification and
  independent control targets, with cooldown/backoff and no direct-route escape.
  Standard sing-box output retains only engine-supported fields and is described
  honestly as latency-based selection.
- Alternate REALITY listeners are opt-in across Ansible defaults, provider
  examples, generated client profiles and disposable CI listener contracts.
- Relevant local checks and protected pull-request checks pass on the delivered
  revisions, with coordinated client integration before producer promotion.
- Deliver positive runnable behavior; refusal-only paths do not satisfy this task.
  Live network availability and deployment are outside this source-only change.
