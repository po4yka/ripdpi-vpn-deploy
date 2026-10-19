---
id: SEC-1792307003680932
title: Repair network protocol correctness audit defects
kind: bug
status: review
area: security
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: network-protocol-correctness
created: 2026-10-18
updated: 2026-10-19
related_tasks: []
---

## Goal

Close the confirmed network protocol audit defects and integrate the reviewed
source through a protected PR without deployment or private fleet access.

## Acceptance criteria

- Every confirmed finding has a focused regression and source evidence.
- Existing SAN and validity fixes and the separately owned Hysteria transit fix
  are integrated without duplicate implementations.
- Complete local gates, security review, structured review and required CI pass.
- The source PR is merged to main; live and conditional risks remain explicit.
