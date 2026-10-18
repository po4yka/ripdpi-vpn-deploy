---
id: XRY-1792265213021342
title: Repair protocol compatibility and audit validation defects
kind: bug
status: doing
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
status_detail: Finish local acceptance after Docker recovery. The full gate exposed a missing local flock prerequisite and one unreproduced TLS fixture failure; retain all guards and rerun the unchanged full make check.
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
