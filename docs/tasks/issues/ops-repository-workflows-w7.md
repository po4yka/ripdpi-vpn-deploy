---
id: CIC-1795329226354380
title: Run plan, deploy, verify, rotate and issue from ops repository workflows
kind: feature
status: backlog
area: ci
priority: high
risk: high
owner: Planner
parent: EPC-1795327697650892
blocked_by: [OPS-1795327950629406, TFR-1795328481774241, SEC-1795328680299474, ANS-1795328948145006, TFR-1795329107889572]
spec_mode: required
openspec_change: cic-1795329226354380-ops-repository-workflows-w7
created: 2026-11-22
updated: 2026-11-22
related_tasks: []
---

## Goal

Requests run in the private ops repository. Automatic previews accept allowed fields on trusted targets. Merged read-only requests stay read-only. Approved mutations reconcile interrupted work, and CI prepares credential changes offline before reviewed deployment.

## Acceptance criteria

- Request and client-artifact validators have unit tests. Exercise read-only merges, concurrent claims, failed receipts and a crash after issuance or apply.
- Authorized: staging preview, deploy and issue runs and scheduled receipts exist on `ops-receipts`.
- The cloud environment has no variables or secrets and the dispatch question is answered.
- The epic's workstation-off drill passes.
