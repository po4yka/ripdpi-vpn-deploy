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
updated: 2026-11-28
status_detail: "Merged in PR 777 (7d96f9bc02); local checks passed. Remote CI is not green: no main ci run that contains this merge passed. Since this merge, contract-sync fails because po4yka/RIPDPI does not vendor node-address-check.schema.json and node-address-check.golden.json; the native runtime jobs fail separately and also failed before this merge. The gate refuses every RIPDPI bundle path until a signed attestation exists, and the producer does not exist yet: it is po4yka/RIPDPI#DGN-1795868945773730. Staging evidence remains: admit one address with a real filtered-side attestation and refuse one without it."
related_tasks: []
---

## Goal

A new node address is checked for TCP and TLS reachability from a filtered-side vantage before any bundle publishes it. A node whose /24 block is already unreachable is refused and recreated with a new address. No liveness decision relies on ICMP alone.

## Acceptance criteria

- A new node is admitted to a bundle only after a TCP and TLS check of its listener from at least one filtered-side vantage passes.
- A node whose /24 block fails the check is refused with an operator message that says to recreate the node.
- Missing vantage or missing result refuses admission; it never passes silently.
- An ICMP result is never the only evidence for admission, liveness or burn decisions.
