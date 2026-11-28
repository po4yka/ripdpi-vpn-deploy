---
id: SEC-1795869545417758
title: Repair privilege and input boundaries from the deployment audit
kind: bug
status: review
area: security
priority: high
risk: high
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: repair-audit-privilege-boundaries
created: 2026-11-28
updated: 2026-11-28
related_tasks: []
---

## Goal

Repair the privilege, privacy and input boundaries identified in the deployment audit.

## Acceptance criteria

- Isolate Realm TLS, protect bearer logs and use anonymous AWG endpoint tags.
- Validate credentials, permissions, service inputs and provider identities.
- Preserve share delivery and report intake, retire owned mirror helpers and exercise the declared operator and CI behavior.
