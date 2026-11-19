---
id: TST-1795087041877687
title: Accept field analytics end to end on staging with a client
kind: feature
status: doing
area: testing
priority: medium
risk: high
owner: Planner
parent: EPC-1795085241910080
blocked_by: [SEC-1795086333272606, SCR-1795086521848661, MON-1795086646495369]
spec_mode: required
openspec_change: tst-1795087041877687-field-analytics-e2e-d7
created: 2026-11-19
updated: 2026-11-19
related_tasks: []
status_detail: "External gate: po4yka/RIPDPI DGN-1795085357320979 (R2 contracts), DGN-1795085498592630 (R3 field report client), DAT-1795085420746769 (R4 bundle v3 failover) must be done and in the tested build."
---

## Goal

On a staging node and a Pixel or emulator, blocking one protocol with DROP or RST shows: the app classifies the stage, the report is ingested, the alert fires, the bundle marks the endpoint degraded and the client fails over.

## Acceptance criteria

- A recorded run for one DROP case and one RST case shows all five observations in order with timestamps.
- Evidence follows the vpn-acceptance skill conventions and the verification file has `staging` and `client` set to passed.
- The block is removed and the node returns to its previous state.
- RIPDPI RIPDPI R2 (DGN-1795085357320979), R3 (DGN-1795085498592630) and R4 (DAT-1795085420746769) are done.
