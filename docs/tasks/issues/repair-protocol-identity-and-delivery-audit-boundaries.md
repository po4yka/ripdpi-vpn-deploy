---
id: SEC-1792301529650686
title: Repair protocol identity and delivery audit boundaries
kind: bug
status: doing
area: security
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: protocol-audit-boundaries
created: 2026-10-18
updated: 2026-10-18
related_tasks: []
---

## Goal

Repair the eight confirmed protocol audit boundaries without changing engines,
deployment scope, credential authority or existing security gates.

## Acceptance criteria

- Unmatched subscription requests retain categorical privacy and generated
  sing-box import/QR targets are served by the existing delivery stack.
- VLESS authentication aliases and AWG cross-instance server/peer conflicts
  refuse before publication; valid controls remain accepted.
- Parsed Snell/Trojan credentials preserve exact admitted values.
- Unsupported RIPDPI Hysteria hopping refuses; every emitted host retains its
  extension metadata and the supported sing-box path remains unchanged.
- Certificate preflight rejects incorrect wildcard SANs and accepts valid SANs.
- Regression, full local, security/review and PR CI evidence is recorded;
  the reviewed source is merged and all required main checks are verified.

## Boundaries

No AWG backend migration, physical-device qualification, deployment, credential
rotation, safety exception or change to PQE HOLD or research admission.
