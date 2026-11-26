---
id: SCR-1795705796387934
title: Carry a per-entry allowlist-regime survivability label in the client bundle
kind: feature
status: backlog
area: scripts
priority: medium
risk: high
owner: Planner
parent: null
blocked_by: []
spec_mode: required
openspec_change: scr-1795705796387934-bundle-allowlist-survivability-label
created: 2026-11-26
updated: 2026-11-26
related_tasks: []
---

## Goal

Each transport entry of the client bundle carries a label (yes, no, unknown) that says whether its transport class can pass under an allowlist regime. The client stops spending attempts on entries that cannot pass.

## Acceptance criteria

- The bundle schema carries one optional label per transport entry with values yes, no and unknown; an absent label means unknown.
- The emitter derives the label from a repository-owned table keyed by transport class and never sets yes without a table entry.
- The validator and negative fixtures reject other values.
- The RIPDPI counterpart consumes the label; the contract copies stay in sync.
