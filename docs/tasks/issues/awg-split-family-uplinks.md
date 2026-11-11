---
id: ANS-1794396376228431
title: Let AmneziaWG use separate IPv4 and IPv6 uplinks
kind: feature
status: doing
area: ansible
priority: high
risk: high
owner: unassigned
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1794396376228431-awg-split-family-uplinks
created: 2026-11-11
updated: 2026-11-11
related_tasks: []
---

## Goal

AmneziaWG runs on providers that attach IPv6 to a separate interface, such as UpCloud (`eth0` IPv4, `eth1` IPv6), with forwarding and NAT pinned per address family to an explicitly named IPv6 uplink, while hosts without that setting keep today's ruleset.

## Acceptance criteria

- `firewall_awg_uplink6_interface` is explicit, validated and never fact-inferred.
- The uplink checker admits IPv4 and IPv6 on their own interfaces and refuses a missing family.
- Split-mode forward and NAT rules pin each family to its uplink and pass `nft -c`; empty or equal values keep the snapshots unchanged.
- An independent security review of the patch reports no unresolved defect.
