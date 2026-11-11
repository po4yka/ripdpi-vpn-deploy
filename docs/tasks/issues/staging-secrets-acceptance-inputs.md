---
id: SCR-1794414233838729
title: Generate complete disposable staging secrets for full-transport cohorts
kind: bug
status: doing
area: scripts
priority: high
risk: standard
owner: unassigned
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-11-11
updated: 2026-11-11
spec_reason: regression-tested-single-module
related_tasks: []
---

## Goal

Observed on staging Node A for `ANS-1794231660855533`: secrets from `scripts/ci-bootstrap-secrets.sh` failed `device-full-staging` dry-runs twice. The geodata section held `example.invalid` placeholders although that cohort enables geodata, and the Hysteria clients lacked the dedicated `runtime-acceptance-hysteria` probe that the transport preflight requires ("Every enabled transport requires its configured probe client"). The generator now creates that probe with its own password and accepts pinned geodata through `GEODATA_*` inputs.

## Acceptance criteria

- Generated Hysteria clients are the device client plus `runtime-acceptance-hysteria`, with distinct passwords.
- `GEODATA_GEOSITE_URL`, `GEODATA_GEOIP_URL` and their sha256 values pass through as a set; a partial or unsafe set refuses before any work; without them the placeholders remain.
- The disposable staging recipe names both inputs.
