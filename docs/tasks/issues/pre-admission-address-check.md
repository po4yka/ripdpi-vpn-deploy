---
id: OPS-1795704918170150
title: Check a new node address from a filtered-side vantage before bundle admission
kind: feature
status: review
area: operations
priority: medium
risk: standard
owner: Planner
parent: null
blocked_by: []
spec_mode: required
openspec_change: ops-1795704918170150-pre-admission-address-check
created: 2026-11-26
updated: 2026-11-27
related_tasks: []
---

## Goal

A new node address is checked for TCP and TLS reachability from a filtered-side vantage before any bundle publishes it. A node whose /24 block is already unreachable is refused and recreated with a new address. No liveness decision relies on ICMP alone.

## Acceptance criteria

- A new node is admitted to a bundle only after a TCP and TLS check of its listener from at least one filtered-side vantage passes.
- A node whose /24 block fails the check is refused with an operator message that says to recreate the node.
- Missing vantage or missing result refuses admission; it never passes silently.
- An ICMP result is never the only evidence for admission, liveness or burn decisions.
