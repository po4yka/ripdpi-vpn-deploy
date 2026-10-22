---
id: SCR-1792659157802819
title: Deliver payload-verified failover and explicit alternate listeners
kind: feature
status: done
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
status_detail: Merged source bf7f9ba has the identical complete tree as tested c77adec1; local component gates, CI 39822440351 and coordinated consumer acceptance passed.
closed_at: "2026-10-22T19:26:24Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Merged source bf7f9baef8130246a255f503909457f676ab46dc has the identical complete tree as tested c77adec1ba63c675552ed71fa8bdebd250275153. Task contracts and ci-fast passed; canonical validate passed in a full isolated branch clone after the original aggregate failed on unrelated-ref gitleaks false positives. CI 39822440351 attempt 2 and all nine protected checks passed. Accepted consumer ede4099f5e53023c03e4e6875cdb8521cb627d56 passed full CI 39815952976 on its identical tested tree. No live, physical-device or deployment acceptance is claimed.
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
