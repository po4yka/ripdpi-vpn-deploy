---
id: OPS-1792820562787120
title: Deliver native Hysteria port hopping to RIPDPI
kind: feature
status: doing
area: operations
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: ripdpi-hysteria-port-hopping
created: 2026-10-24
updated: 2026-10-24
related_tasks: ["po4yka/RIPDPI#OUT-1792820412611017"]
---

## Goal

Deliver the existing Hysteria hopping policy through recipient export to the qualified native RIPDPI client.

## Acceptance criteria

- Valid range and fixed interval survive standard fields and RIPDPI extras unchanged.
- Invalid interval values fail before output or publication without credential disclosure.
- The paired client passes positive real-server traffic across three scheduled destination-port changes, including IPv6 and Salamander; refusal-only behavior does not qualify.
- Relevant local checks and terminal hosted checks pass, and both source changes reach main through PRs.
- No live fleet or physical-device acceptance is inferred from source tests.
