---
id: ANS-1792773060904443
title: Make source build process cleanup deterministic
kind: bug
status: done
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
closed_at: "2026-10-24T09:06:57Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: PR 380 merged as ec655f037b5a1b7a26d8ddf4c673ef4e55791701 with the identical tested tree. Full make check passed at dd9fef311cde792af2a2d94ff0ee5c7f7427e6e9; run 40069354263 and all required checks passed. All 12 review threads are resolved; the completed change is archived.
---

## Goal

Complete source builds and reclaim their owned foreground processes on Linux and macOS without false cleanup failures or surviving descendants.

## Acceptance criteria

- A completed foreground build can publish its exact outputs and receipt after confirmed process cleanup.
- Cancellation, timeout and an exited leader with live descendants stop the owned process group before the project lock is released.
- Unconfirmed cleanup fails without publication or loss of the primary failure.
- Regression tests exercise the observed local failures without skipped cases or weaker safety assertions.
- The full local `make check` and protected PR checks pass before source integration.
