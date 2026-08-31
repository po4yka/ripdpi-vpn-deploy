---
id: SEC-1788187456764401
title: Preserve return traffic through the UpCloud stateless firewall
kind: bug
status: doing
area: security
priority: critical
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1788187456764401-upcloud-stateless-return-path
created: 2026-08-31
updated: 2026-08-31
related_tasks: []
---

## Goal

Enable the UpCloud Public & Utility firewall without breaking server-initiated
TCP/UDP traffic or exposing SSH beyond the reviewed management CIDRs.

## Acceptance criteria

- The server resource keeps the provider firewall disabled until an operator
  explicitly promotes a node whose guest stateful firewall and SSH path were
  verified.
- The enabled provider ruleset permits IPv4 and IPv6 TCP/UDP replies to the
  canonical Linux ephemeral range, plus DHCP bootstrap traffic, before the
  terminal inbound drops.
- Terraform tests prove the activation default, return-path matrix, CIDR-scoped
  SSH, rule ordering, and range validation without provider access.
- One authorized isolated staging node proves package bootstrap, DNS, outbound
  TCP/UDP, required public listeners, and strict SSH before and after provider
  firewall activation.
- Exact-resource guarded cleanup and provider absence verification complete
  before the 47-hour hard deadline; production remains unchanged.
