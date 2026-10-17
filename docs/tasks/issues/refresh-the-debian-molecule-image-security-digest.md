---
id: CIC-1792268380780556
title: Refresh the Debian Molecule image security digest
kind: bug
status: review
area: ci
priority: high
risk: standard
owner: Protocol maintenance
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-10-18
updated: 2026-10-18
spec_reason: dependency-only
related_tasks: [XRY-1792265213021342]
status_detail: Both unchanged Trivy scans, cloud-init schema and all affected Molecule jobs passed at e2aa874c25b149575bfa520f5b2d48f54cfde002 in run 39067975140. The unrelated Naive native fixture failure keeps the parent PR draft.
---

## Goal

Clear the existing Debian test-image scan failure that blocks protocol repair CI.
Use the already published immutable image that passes the unchanged security policy.

## Acceptance criteria

- Every active Debian test-image consumer uses the scanned digest.
- The digest clears the 23 fixable HIGH findings in linux-libc-dev and libexpat.
- Pin and cloud-init regressions, affected Molecule jobs and image-scan pass.
- No scan ignore, severity change, production image or new publication is used.
