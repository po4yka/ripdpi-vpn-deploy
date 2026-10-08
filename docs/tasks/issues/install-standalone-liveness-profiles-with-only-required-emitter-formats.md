---
id: SCR-1791467099957833
title: Install standalone liveness profiles with only required emitter formats
kind: bug
status: dropped
area: scripts
priority: high
risk: standard
owner: operator
parent: null
blocked_by: []
spec_mode: required
openspec_change: scr-1791467099957833-install-standalone-liveness-profiles-with-only-required-emitter-formats
created: 2026-10-08
updated: 2026-10-08
related_tasks: []
closed_at: "2026-10-08T15:25:23Z"
closed_reason: Owner cancelled acceptance and requested removal of all acceptance resources
evidence_summary: Live acceptance is cancelled, not completed. Already merged implementation is preserved; temporary provider and local acceptance resources are being retired.
---

## Goal

Install a standalone P1 XHTTP sentinel through the canonical installer without requesting an unsupported sing-box profile.

## Acceptance criteria

- Selected profiles determine which canonical JSON emitters run; AWG-only needs neither.
- Required emitter errors still refuse before remote writes, with parser and identity checks intact.
- Focused tests and required source gates pass; real P1 onboarding and authenticated XHTTP proof remain mandatory before closure.
