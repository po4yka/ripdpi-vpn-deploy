---
id: SEC-1793385377599445
title: Harden REALITY admission and repair client delivery defects
kind: feature
status: doing
area: security
priority: high
risk: high
owner: unassigned
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1793385377599445-reality-admission-delivery-repairs
created: 2026-10-30
updated: 2026-10-30
related_tasks: []
---

## Goal

P0 REALITY nodes bound the client time window. Production Xray acquisition admits only reviewed pins. Probes, share URIs and bundle topology describe the recipient path that devices use. New XHTTP paths are unguessable, and the published example path is refused.

## Acceptance criteria

- Every requirement in `openspec/changes/sec-1793385377599445-reality-admission-delivery-repairs/specs/security/reality-admission-delivery-integrity/spec.md` has passing local evidence.
- `make check` and PR CI pass on the head SHA.
- Dry-run, staging, live and client evidence are recorded after an authorized deploy before archive.
