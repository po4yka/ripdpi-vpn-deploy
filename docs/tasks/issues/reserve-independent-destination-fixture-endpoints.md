---
id: CIC-1791955671832430
title: Reserve independent destination fixture endpoints
kind: bug
status: review
area: ci
priority: high
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-10-14
updated: 2026-10-14
spec_reason: test-only
related_tasks: []
status_detail: A real UDP collision reproduced the old failure; bounded paired-socket admission and all 83 affected portable cases now pass without changing production contracts or deadlines.
---

## Goal

Keep the real-socket destination gateway fixture usable when its TCP-selected numeric port is already occupied in UDP. This fixture gates runtime acceptance source checks.

## Acceptance criteria

- TCP and UDP each retain their own kernel-reserved socket on the same required gateway port.
- A candidate is admitted only after both protocol leases succeed; rejected sockets are closed, allocation is finite and errors other than address collisions propagate.
- A regression holding a real conflicting UDP lease fails before the fix and passes afterward.
- The complete affected destination-boundary and Xray portable modules pass with every deadline and assertion intact.
