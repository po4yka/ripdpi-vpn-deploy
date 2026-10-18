---
id: XRY-1792265213021342
title: Repair protocol compatibility and audit validation defects
kind: bug
status: done
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
status_detail: Local make check and exact source/main CI passed. Preserve accepted main source 4f7b54e4480039526d9c8febca033932506f4a56 and commit the review snapshot before canonical archival.
closed_at: "2026-10-18T11:21:16Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Accepted source main 4f7b54e4480039526d9c8febca033932506f4a56 equals tested fbfc7af8; source CI39113178648 and main CI39117467457 each passed92 jobs. Full local make check at fa343371 exited0:7957 portable,45 subtests,65 Bats,322 vpnd and206 transfer cases; later docs and fixture deltas passed their checks. PQE HOLD preserved; no deployment."
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
