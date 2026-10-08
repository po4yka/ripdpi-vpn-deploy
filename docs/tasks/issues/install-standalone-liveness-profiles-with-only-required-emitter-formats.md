---
id: SCR-1791467099957833
title: Install standalone liveness profiles with only required emitter formats
kind: bug
status: doing
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
---

## Goal

Install a standalone P1 XHTTP sentinel through the canonical installer without requesting an unsupported sing-box profile.

## Acceptance criteria

- Selected profiles determine which canonical JSON emitters run; AWG-only needs neither.
- Required emitter errors still refuse before remote writes, with parser and identity checks intact.
- Focused tests and required source gates pass; real P1 onboarding and authenticated XHTTP proof remain mandatory before closure.
