---
id: SEC-1795260338347014
title: Bound the capabilities of the transport generation controller
kind: feature
status: backlog
area: security
priority: medium
risk: high
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1795260338347014-transport-generation-capability-bound
created: 2026-11-21
updated: 2026-11-21
related_tasks: [ANS-1795163654691828]
---

## Goal

`ripdpi-transport-generation.service` keeps only the root capabilities that its operations need, so a defect in the controller cannot use the rest, and frontend control and recovery still work. Follow-up of the fleet audit change `ANS-1795163654691828`, which declined the bound because a wrong set stops every frontend and only native lanes can prove it.

## Acceptance criteria

- The rendered unit has a `CapabilityBoundingSet`, and the role note gives the operation that needs each listed capability.
- The native transport lanes and full-stack Molecule pass with the bounded unit.
- A disposable staging node recovers all frontends after a reboot and refreshes the WARP namespace under the bound, with no capability error in the journal.
