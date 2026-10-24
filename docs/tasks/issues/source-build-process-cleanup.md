---
id: ANS-1792773060904443
title: Make source build process cleanup deterministic
kind: bug
status: review
area: ansible
priority: high
risk: high
owner: process-maintainer
parent: null
blocked_by: []
spec_mode: required
openspec_change: source-build-process-cleanup
created: 2026-10-23
updated: 2026-10-24
related_tasks: [CIC-1792759317705110]
status_detail: Source cleanup and complete local and hosted gates passed; ready for archival.
---

## Goal

Complete source builds and reclaim their owned foreground processes on Linux and macOS without false cleanup failures or surviving descendants.

## Acceptance criteria

- A completed foreground build can publish its exact outputs and receipt after confirmed process cleanup.
- Cancellation, timeout and an exited leader with live descendants stop the owned process group before the project lock is released.
- Unconfirmed cleanup fails without publication or loss of the primary failure.
- Regression tests exercise the observed local failures without skipped cases or weaker safety assertions.
- The full local `make check` and protected PR checks pass before source integration.
