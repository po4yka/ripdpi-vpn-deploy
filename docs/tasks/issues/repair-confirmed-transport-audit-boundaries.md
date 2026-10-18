---
id: SEC-1792306834441683
title: Repair confirmed transport audit boundaries
kind: bug
status: done
area: security
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: transport-audit-boundaries
created: 2026-10-18
updated: 2026-10-18
related_tasks: []
closed_at: "2026-10-18T12:54:23Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: PR 334 merged at 365b08b680963d1bdd8c879b005467e24913b482. Post-merge CI run 39122200716 and all nine required checks passed. Focused portable/native coverage and source/security reviews passed; source-only scope.
---

## Goal

Repair the confirmed transport audit failures without deploying runtime changes.

## Acceptance criteria

- Hopping preserves forwarded UDP and every exported Hysteria endpoint retains its metadata.
- Split-hop prevents direct original traffic while its tunnel is stopped; strict egress admits enabled overlay needs.
- AWG parameters match the pinned engine and DNS-Morph rejects invalid keys or implicit echo mode before host changes.
- WARP key format matches its keyring suffix; operator documentation states measured capability boundaries.
- Regression tests, required source gates, structured review and protected PR checks pass before merge.
