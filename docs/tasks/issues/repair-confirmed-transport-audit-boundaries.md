---
id: SEC-1792306834441683
title: Repair confirmed transport audit boundaries
kind: bug
status: doing
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
---

## Goal

Repair the confirmed transport audit failures without deploying runtime changes.

## Acceptance criteria

- Hopping preserves forwarded UDP and every exported Hysteria endpoint retains its metadata.
- Split-hop prevents direct original traffic while its tunnel is stopped; strict egress admits enabled overlay needs.
- AWG parameters match the pinned engine and DNS-Morph rejects invalid keys or implicit echo mode before host changes.
- WARP key format matches its keyring suffix; operator documentation states measured capability boundaries.
- Regression tests, required source gates, structured review and protected PR checks pass before merge.
