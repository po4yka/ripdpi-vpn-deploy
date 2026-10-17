---
id: XRY-1792265213021342
title: Repair protocol compatibility and audit validation defects
kind: bug
status: blocked
area: xray-config
priority: high
risk: high
owner: Protocol maintenance
parent: null
blocked_by: []
spec_mode: required
openspec_change: protocol-audit-compatibility
created: 2026-10-17
updated: 2026-10-18
related_tasks: [CIC-1792268380780556]
status_detail: PR324 merged as a620c9dfb0ef41e13410a932016d88ec6785b66d after exact-head full CI success. Local make check remains blocked by Docker timeout 125 and unverified container cleanup; the local validation step stays open.
---

## Goal

Deliver compatible client artifacts, safe optional transport configuration and
early identity validation while keeping PQE HOLD.

## Acceptance criteria

- Incompatible P0 mux delivery and malformed or wire-duplicate identities refuse.
- Official mtg archive extraction and FakeTLS native checks pass.
- Naive error logs retain no CONNECT metadata in native failure-path checks.
- Real pinned P0 and Snell compatibility checks pass in required CI.
- PQE HOLD guards, make check and independent review pass.
- The reviewed PR passes exact-head CI before merge to main.
