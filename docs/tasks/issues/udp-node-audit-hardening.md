---
id: ANS-1795163654691828
title: Close UDP transport, firewall and split-hop gaps from the fleet audit
kind: bug
status: doing
area: ansible
priority: high
risk: high
owner: Security remediation
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1795163654691828-udp-node-audit-hardening
created: 2026-11-20
updated: 2026-11-20
related_tasks: []
---

## Goal

A UDP transport node answers on TCP where it answers on UDP, does not send at a fixed rate, has an explicit connection tracking budget and carries TCP through the AmneziaWG tunnel on a constrained path; split-hop egress works on any provider uplink name and cannot reach private destinations. Source: the 2026-11-20 repository and live fleet audit.

## Acceptance criteria

- With `hysteria_masquerade_tcp`, the Hysteria configuration and the listener manifest carry the TCP masquerade listeners, without TCP/80 when native ACME is configured; `vpn-p2-udp` enables it and selects a BBR congestion default.
- The baseline sysctl policy sets the connection tracking budget and UDP timeouts and `fs.file-max` 2097152.
- The firewall clamps forwarded AmneziaWG TCP to the instance MTU, accepts scoped DHCPv4 replies and drops split-hop egress traffic to private destinations; the AmneziaWG MTU default is 1280.
- Split-hop egress follows the observed uplink and the ingress listen port, and its policy loader is sandboxed and stays active.
- Production admission refuses the published junk triple or padding pair; the cohort fingerprint handles an absent `wire_profile` and refuses other gaps without changing valid output.
- A node-local masquerade origin, a per-source connection limit, a listener family split, the generation controller capability set and the split-hop ingress `PostDown` stay out of scope with recorded reasons.
