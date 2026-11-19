---
id: MON-1795086646495369
title: Detect network blocks from sentinel and client-report divergence
kind: feature
status: review
area: monitoring
priority: medium
risk: high
owner: Implementer
parent: EPC-1795085241910080
blocked_by: [SEC-1795086333272606, MON-1795086175387484]
spec_mode: required
openspec_change: mon-1795086646495369-network-block-detection-d5
created: 2026-11-19
updated: 2026-11-19
related_tasks: []
---

## Goal

An alert says a protocol is blocked in a network (ASN) when the sentinel reports healthy but client failures spike for that ASN, and it outputs a rotation hint for the fleet-rotate PLAN; the operator still decides.

## Acceptance criteria

- Alert "blocked in network" fires for the divergence and not when the sentinel is also down.
- The alert annotation carries protocol, ASN, country, failure stage mix and a rotation hint text.
- The hint is output for `scripts/fleet-rotate.sh` PLAN mode and never executes rotation.
- promtool tests cover firing, non-firing and low-sample cases.
