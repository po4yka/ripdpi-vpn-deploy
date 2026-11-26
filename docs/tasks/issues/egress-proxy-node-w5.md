---
id: ANS-1795328948145006
title: Add a secretless egress proxy node for provider APIs
kind: feature
status: doing
area: ansible
priority: high
risk: high
owner: Planner
parent: EPC-1795327697650892
blocked_by: [TFR-1795328347526492, TFR-1795328481774241, SEC-1795328680299474]
spec_mode: required
openspec_change: ans-1795328948145006-egress-proxy-node-w5
created: 2026-11-22
updated: 2026-11-26
related_tasks: []
---

## Goal

A Hetzner node with a retained IPv4 runs a CONNECT-only, Tailnet-only, allowlisted proxy with no secrets, and provider API allowlists name only its address.

## Acceptance criteria

- Molecule proves method, port, host and IP-literal denials and the unit hardening score. Include numeric targets with allowlisted PTR names.
- `tofu test` proves the address survives server replacement.
- Authorized: the provider proof log shows every provider and the B2 backend through the proxy; Vultr lists only the egress address; stopped-service and lost-server drills restore proxied access.
