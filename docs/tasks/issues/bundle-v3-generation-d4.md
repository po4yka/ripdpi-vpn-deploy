---
id: SCR-1795086521848661
title: Generate ripdpi-bundle v3 with endpoint health and field-report config
kind: feature
status: review
area: scripts
priority: high
risk: high
owner: Implementer
parent: EPC-1795085241910080
blocked_by: [SCR-1795085709140075, MON-1795086175387484]
spec_mode: required
openspec_change: scr-1795086521848661-bundle-v3-generation-d4
created: 2026-11-19
updated: 2026-11-19
related_tasks: [po4yka/RIPDPI#DGN-1795704789266331]
---

## Goal

`scripts/emit-bundle.sh` emits ripdpi-bundle v3 with per-endpoint health derived from protocol-liveness quorum and cascade-leg-health, a `field_report` block, and a cohort token with a defined rotation.

## Acceptance criteria

- The generated bundle validates against the v3 schema from D1 and v2 output is no longer produced.
- Endpoint `health` reflects the protocol-liveness quorum and cascade-leg-health; absent or stale input yields `unknown`, never `healthy`.
- `field_report.cohort_token` is shared per cohort, not per device, and rotates by an operator command that keeps the previous token valid for D2 for a bounded overlap.
- `max_reports_per_day` and `endpoint` come from configuration.
