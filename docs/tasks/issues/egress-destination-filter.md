---
id: SEC-1794156917837664
title: Block unsafe recipient destinations at the egress boundary
kind: feature
status: doing
area: security
priority: medium
risk: high
owner: Operator
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1794156917837664-egress-destination-filter
created: 2026-11-08
updated: 2026-11-12
related_tasks: []
---

## Goal

Operators can deny known unsafe recipient destinations for P0, P1 and Hysteria2 at the transport-egress boundary from one pinned list, with the policy disabled by default and bad input unable to replace an accepted generation.

## Acceptance criteria

- With the toggle off, rendered configuration and behavior do not change.
- With the toggle on, listed names, their subdomains and listed ranges receive no connection or packet on each of the three paths, and unlisted destinations behave as before.
- Moving URLs, digest mismatches, malformed or oversized lists and lists that deny control paths are refused before the accepted generation stops.
- Denials use the existing failure and record no destination.
- The entry limit comes from a measurement on the smallest node class.
- Documentation states that AmneziaWG and client-direct traffic are not covered and describes the client-side block.
- Staging and a client device show the behavior before production enablement.
