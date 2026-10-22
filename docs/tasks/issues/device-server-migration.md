---
id: OPS-1792673523985723
title: Migrate devices safely during server replacement
kind: feature
status: doing
area: operations
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: device-server-migration
created: 2026-10-22
updated: 2026-10-22
related_tasks: ["po4yka/RIPDPI#TRN-1792673614153980"]
---

## Goal

Move affected devices to a replacement server through reviewed credential
preparation, stable subscription publication, resumable progress and explicit
client-path acceptance before old-node retirement.

## Acceptance criteria

- Discover the exact affected active delivery set and preserve per-device
  identities, unrelated target users and source access during overlap.
- Publish usable replacement profiles to existing token URLs with unchanged
  expiry, revocation enforcement, exact-byte reconciliation and rollback.
- Distinguish published, received and tested states; paired client exports are
  explicit and work for all four baseline transports without a mandatory backend.
- Gate blue-green completion on every participant; interrupted/concurrent/stale
  operations fail safely and can resume known completed boundaries.
- Real local publication and encrypted transaction regressions, client tests,
  required local gates, independent review and protected PR/main CI pass.
- Refusal-only paths, mocks or controller receipts do not prove live server or
  physical-device acceptance; no such operation is included in this source task.
