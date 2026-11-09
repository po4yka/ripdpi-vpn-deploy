---
id: SCR-1794116837161459
title: Issue a device privately when the fleet has no subscription publisher
kind: feature
status: done
area: scripts
priority: high
risk: high
owner: operator
parent: null
blocked_by: []
spec_mode: required
openspec_change: scr-1794116837161459-device-private-delivery
created: 2026-11-08
updated: 2026-11-09
related_tasks: []
closed_at: "2026-11-09T06:39:00Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: PRs 532, 533 and 538 merged with green required checks; operation b5f72cff issued the device privately on three production nodes and reached phase complete.
---

## Goal

An operator can issue and refresh a `ripdpi` or `singbox` device with `make device-lifecycle` on a fleet without a subscription publisher. The device gets one private recipient artifact and no public subscription endpoint is needed. The first consumer is `personal-pixel-incy`, whose INCY links come from `make emit-incy`.

## Acceptance criteria

- With `publishers: []`, `ripdpi` and `singbox` issue and refresh complete with a private artifact: rendered profile, AWG configurations, `subscription_url: null`, and no minted or published grant.
- A manifest with no publisher and a non-empty expiry is refused before any encrypted intent.
- Fleets with publishers and native delivery keep their behavior; revocation is unchanged.
- `personal-pixel-incy` is issued on the production fleet through this path as a separately authorized step.
