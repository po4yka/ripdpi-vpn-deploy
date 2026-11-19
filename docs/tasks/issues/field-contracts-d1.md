---
id: SCR-1795085709140075
title: Define client field-report v1 and ripdpi-bundle v3 contracts
kind: feature
status: review
area: scripts
priority: high
risk: high
owner: Planner
parent: EPC-1795085241910080
blocked_by: []
spec_mode: required
openspec_change: scr-1795085709140075-field-contracts-d1
created: 2026-11-19
updated: 2026-11-19
related_tasks: []
status_detail: Independent network-hint review findings fixed and verified locally; re-review pending
---

## Goal

This repository is the canonical source of the client-field-report v1 schema and the ripdpi-bundle v3 schema, with golden and negative fixtures and validator coverage. Bundle v3 replaces v2.

## Acceptance criteria

- `contract/client-field-report.schema.json` v1 validates the golden report and rejects every negative fixture.
- `contract/ripdpi-bundle.schema.json` has `schema_version` const 3 and rejects v2 documents.
- `scripts/validate-bundle.py` and a new report validator cover both schemas; `docs/reference/ripdpi-bundle.md` documents v3 and names the v2 break.
- Counterpart RIPDPI R2 can vendor the schemas and fixtures unchanged.
