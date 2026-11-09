---
id: ANS-1794231660855533
title: Route family transport egress through the split-hop exit node
kind: feature
status: doing
area: ansible
priority: high
risk: high
owner: unassigned
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1794231660855533-split-hop-family-egress
created: 2026-11-09
updated: 2026-11-09
related_tasks: []
---

## Goal

A split-hop Node A can opt in with `vpn.split_hop_family_egress` so that every family transport's recipient traffic (Xray P0/P1, Hysteria2, AmneziaWG) leaves from Node B. The client-facing address then never sources a recipient flow, which removes both the application-reported egress match and the per-IP dual-role signal for that address. Loss of the tunnel stops the traffic instead of falling back to Node A's uplink.

## Acceptance criteria

- The split-hop policy marks the transport normalizer and direct gateway UIDs and forwarded AWG IPv4 originals, rejects their IPv6 and drops non-tunnel originals; the tunnel uses loose reverse-path filtering.
- The firewall forwards and NATs AWG over the tunnel in family scope and extends the shared UID guard.
- The family direct gateway resolves and dials IPv4 only; `site.yml` refuses family scope without the responder or with direct-egress transports.
- Native, unit and snapshot regressions pass; decision 0003, role notes and the pilot guide describe the scope. Live acceptance stays operator-authorized.
